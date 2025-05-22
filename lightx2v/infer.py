import argparse
import torch
import torch.distributed as dist
import json

from lightx2v.utils.envs import *
from lightx2v.utils.utils import seed_all
from lightx2v.utils.profiler import ProfilingContext
from lightx2v.utils.set_config import set_config
from lightx2v.utils.registry_factory import RUNNER_REGISTER

from lightx2v.models.runners.hunyuan.hunyuan_runner import HunyuanRunner
from lightx2v.models.runners.wan.wan_runner import WanRunner
from lightx2v.models.runners.wan.wan_causal_runner import WanCausalRunner
from lightx2v.models.runners.graph_runner import GraphRunner

from lightx2v.common.ops import *


def init_runner(config):
    seed_all(config.seed)

    if config.parallel_attn_type:
        dist.init_process_group(backend="nccl")

    if CHECK_ENABLE_GRAPH_MODE():
        default_runner = RUNNER_REGISTER[config.model_cls](config)
        runner = GraphRunner(default_runner)
    else:
        runner = RUNNER_REGISTER[config.model_cls](config)
    return runner


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_cls", type=str, required=True, choices=["wan2.1", "hunyuan", "wan2.1_causal"], default="hunyuan")
    parser.add_argument("--task", type=str, choices=["t2v", "i2v"], default="t2v")
    parser.add_argument("--model_path", type=str, required=True)
    parser.add_argument("--config_json", type=str, required=True)

    parser.add_argument("--prompt", type=str, required=True)
    parser.add_argument("--negative_prompt", type=str, default="")
    parser.add_argument("--image_path", type=str, default="", help="The path to input image file or path for image-to-video (i2v) task")
    parser.add_argument("--save_video_path", type=str, default="./output_lightx2v.mp4", help="The path to save video path/file")
    args = parser.parse_args()
    print(f"args: {args}")

    with ProfilingContext("Total Cost"):
        config = set_config(args)
        print(f"config:\n{json.dumps(config, ensure_ascii=False, indent=4)}")
        runner = in_runner(config)

        runner.run_pipeline()
