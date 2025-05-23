import os
import torch
from lightx2v.models.networks.hunyuan.weights.pre_weights import HunyuanPreWeights
from lightx2v.models.networks.hunyuan.weights.post_weights import HunyuanPostWeights
from lightx2v.models.networks.hunyuan.weights.transformer_weights import HunyuanTransformerWeights
from lightx2v.models.networks.hunyuan.infer.pre_infer import HunyuanPreInfer
from lightx2v.models.networks.hunyuan.infer.post_infer import HunyuanPostInfer
from lightx2v.models.networks.hunyuan.infer.transformer_infer import HunyuanTransformerInfer
from lightx2v.models.networks.hunyuan.infer.feature_caching.transformer_infer import HunyuanTransformerInferTaylorCaching, HunyuanTransformerInferTeaCaching

import lightx2v.attentions.distributed.ulysses.wrap as ulysses_dist_wrap
import lightx2v.attentions.distributed.ring.wrap as ring_dist_wrap


class HunyuanModel:
    pre_weight_class = HunyuanPreWeights
    post_weight_class = HunyuanPostWeights
    transformer_weight_class = HunyuanTransformerWeights

    def __init__(self, model_path, config, device, args):
        self.model_path = model_path
        self.config = config
        self.device = device
        self.args = args
        self._init_infer_class()
        self._init_weights()
        self._init_infer()

        if config["parallel_attn_type"]:
            if config["parallel_attn_type"] == "ulysses":
                ulysses_dist_wrap.parallelize_hunyuan(self)
            elif config["parallel_attn_type"] == "ring":
                ring_dist_wrap.parallelize_hunyuan(self)
            else:
                raise Exception(f"Unsuppotred parallel_attn_type")

        if self.config["cpu_offload"]:
            self.to_cpu()

    def _init_infer_class(self):
        self.pre_infer_class = HunyuanPreInfer
        self.post_infer_class = HunyuanPostInfer
        if self.config["feature_caching"] == "NoCaching":
            self.transformer_infer_class = HunyuanTransformerInfer
        elif self.config["feature_caching"] == "TaylorSeer":
            self.transformer_infer_class = HunyuanTransformerInferTaylorCaching
        elif self.config["feature_caching"] == "Tea":
            self.transformer_infer_class = HunyuanTransformerInferTeaCaching
        else:
            raise NotImplementedError(f"Unsupported feature_caching type: {self.config['feature_caching']}")

    def _load_ckpt(self):
        if self.args.task == "t2v":
            ckpt_path = os.path.join(self.model_path, "hunyuan-video-t2v-720p/transformers/mp_rank_00_model_states.pt")
        else:
            ckpt_path = os.path.join(self.model_path, "hunyuan-video-i2v-720p/transformers/mp_rank_00_model_states.pt")
        weight_dict = torch.load(ckpt_path, map_location=self.device, weights_only=True)["module"]
        return weight_dict

    def _init_weights(self):
        weight_dict = self._load_ckpt()
        # init weights
        self.pre_weight = self.pre_weight_class(self.config)
        self.post_weight = self.post_weight_class(self.config)
        self.transformer_weights = self.transformer_weight_class(self.config)
        # load weights
        self.pre_weight.load_weights(weight_dict)
        self.post_weight.load_weights(weight_dict)
        self.transformer_weights.load_weights(weight_dict)

    def _init_infer(self):
        self.pre_infer = self.pre_infer_class(self.config)
        self.post_infer = self.post_infer_class(self.config)
        self.transformer_infer = self.transformer_infer_class(self.config)

    def set_scheduler(self, scheduler):
        self.scheduler = scheduler
        self.pre_infer.set_scheduler(scheduler)
        self.post_infer.set_scheduler(scheduler)
        self.transformer_infer.set_scheduler(scheduler)

    def to_cpu(self):
        self.pre_weight.to_cpu()
        self.post_weight.to_cpu()
        self.transformer_weights.to_cpu()

    def to_cuda(self):
        self.pre_weight.to_cuda()
        self.post_weight.to_cuda()
        self.transformer_weights.to_cuda()

    @torch.no_grad()
    def infer(self, inputs):
        if self.config["cpu_offload"]:
            self.pre_weight.to_cuda()
            self.post_weight.to_cuda()

        inputs = self.pre_infer.infer(self.pre_weight, inputs)
        inputs = self.transformer_infer.infer(self.transformer_weights, *inputs)
        self.scheduler.noise_pred = self.post_infer.infer(self.post_weight, *inputs)

        if self.config["cpu_offload"]:
            self.pre_weight.to_cpu()
            self.post_weight.to_cpu()
        if self.config["feature_caching"] == "Tea":
            self.scheduler.cnt += 1
            if self.scheduler.cnt == self.scheduler.num_steps:
                self.scheduler.cnt = 0
