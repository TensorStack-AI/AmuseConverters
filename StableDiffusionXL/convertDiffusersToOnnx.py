import config
import os
import argparse
import json
import shutil
import warnings
from pathlib import Path
from olive.workflows import run as olive_run
from olive.model import ONNXModelHandler

def optimize(script_dir: str, model_input: str, model_output: Path, submodel_names: list[str]):
    model_info = {}
    model_dir = model_input
   
    for submodel_name in submodel_names:
        print(f"\nOptimizing {submodel_name}...")
        if submodel_name in ("tokenizer", "tokenizer_2"):
            print(f"Optimizing {submodel_name} complete.")
            continue

        olive_config = None
        with (script_dir / f"config_{submodel_name}.json").open() as fin:
            olive_config = json.load(fin)

        olive_config["input_model"]["config"]["model_path"] = model_dir
        run_res = olive_run(olive_config)
        save_onnx_submodel(script_dir, submodel_name, model_info)
        print(f"Optimizing {submodel_name} complete.")

    save_onnx_models(model_dir, model_info, model_output, submodel_names)
    return model_info


def save_onnx_models(model_dir, model_info, model_output, submodel_names):
    model_dir = Path(model_dir)
    model_output.mkdir(parents=True, exist_ok=True)
    
    for submodel_name in submodel_names:
        print(f"Saving {submodel_name} model...")
        if submodel_name in ("tokenizer", "tokenizer_2"):
            if os.path.exists(model_dir / submodel_name):
                shutil.copytree(model_dir / submodel_name, model_output / submodel_name, ignore=shutil.ignore_patterns("*tokenizer_config.json"))
            continue
        
        dst_dir = model_output / submodel_name
        dst_dir.mkdir(parents=True, exist_ok=True)

        # model.onnx & model.onnx.data
        src_path = model_info[submodel_name]["path"]
        src_data_path = src_path.parent / "model.onnx.data"
        shutil.copy(src_path, dst_dir)
        if os.path.exists(src_data_path):
            shutil.copy(src_data_path, dst_dir)

    print(f"Model Output: {model_output}")


def save_onnx_submodel(script_dir, submodel_name, model_info):
    footprints_file_path = (script_dir / ".olive-cache" / "models" / submodel_name / "footprints.json")
    with footprints_file_path.open("r") as footprint_file:
        footprints = json.load(footprint_file)

        optimizer_footprint = None
        for footprint in footprints.values():
            if footprint["from_pass"] == "OnnxFloatToFloat16":
                optimizer_footprint = footprint
            elif footprint["from_pass"] == "OnnxPeepholeOptimizer":
                optimizer_footprint = footprint
            elif footprint["from_pass"] == "OrtTransformersOptimization":
                optimizer_footprint = footprint
        assert optimizer_footprint

        optimized_olive_model = ONNXModelHandler(**optimizer_footprint["model_config"]["config"])
        model_info[submodel_name] = {
            "path": Path(optimized_olive_model.model_path)
        }


def clean(script_dir):
    shutil.rmtree(script_dir / ".olive-cache", ignore_errors=True)


def parse_common_args(raw_args):
    parser = argparse.ArgumentParser("Common arguments")
    parser.add_argument("--input", required=True, type=str)
    parser.add_argument("--output", default=None, type=Path)
    parser.add_argument("--modules", default="tokenizer,tokenizer_2,text_encoder,text_encoder_2,vae_encoder,vae_decoder,unet,controlnet", help="The modules to convert `tokenizer,tokenizer_2,text_encoder,text_encoder_2,vae_encoder,vae_decoder,unet,controlnet`")
    parser.add_argument("--clean", default=False, action="store_true", help="Deletes the Olive cache")
    parser.add_argument("--vae_fp16_fix", default=False, action="store_true", help="Use 'madebyollin/sdxl-vae-fp16-fix' vae model")
    return parser.parse_known_args(raw_args)


def main(raw_args=None):
    common_args, extra_args = parse_common_args(raw_args)
    model_input = common_args.input
    model_output = common_args.output
    script_dir = Path(__file__).resolve().parent

    if model_output is None:
        model_output = Path(model_input) / "_onnx"
        shutil.rmtree(model_output, ignore_errors=True)

    if common_args.clean:
        clean(script_dir)

    submodel_names = common_args.modules.split(",")
    config.vae_fp16_fix = common_args.vae_fp16_fix

    print('Olive Conversion - SDXL Model')
    print('--------------------------------------')
    print(f'Input: {model_input}')
    print(f'Output: {model_output}')
    print(f'Modules: {submodel_names}')
    print(f'vae_fp16_fix: {common_args.vae_fp16_fix}')
    print('--------------------------------------')
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        optimize(script_dir, model_input, model_output, submodel_names)

    clean(script_dir)
    print('Olive SDXL Conversion Complete.')


if __name__ == "__main__":
    main()
