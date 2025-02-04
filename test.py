from __future__ import division
import os
import time
import tensorflow as tf
import tensorflow.compat.v1 as tfv1
import numpy as np
import argparse
import subprocess
import imageio
from model.network import UNet as UNet
from model.network import UNet_SE as UNet_SE
from glob import glob
import random
from tqdm import tqdm

# Disable eager execution for compatibility with TF 1.x code
tfv1.disable_eager_execution()

seed = 2019
np.random.seed(seed)
tfv1.set_random_seed(seed)
random.seed(seed)

parser = argparse.ArgumentParser()
parser.add_argument("--model", default="full_global_lp", help="path to folder containing the model")
parser.add_argument("--testset", default="./data/demo", help="path to test set")
ARGS = parser.parse_args()
model = ARGS.model

def get_free_gpu():
    try:
        result = subprocess.check_output(
            "nvidia-smi --query-gpu=index,memory.free --format=csv,noheader,nounits", 
            shell=True
        ).decode('utf-8').strip()

        gpu_memory = [tuple(map(str.strip, line.split(','))) for line in result.splitlines()]
        gpu_memory_dict = {int(index): int(memory) for index, memory in gpu_memory}

        if not gpu_memory_dict:
            raise ValueError("No GPU memory information found.")

        free_gpu_index = max(gpu_memory_dict, key=gpu_memory_dict.get)
        return free_gpu_index
    except Exception as e:
        print("Error selecting GPU: {}".format(e))
        return 0  # Default to GPU 0 if anything goes wrong

os.environ["CUDA_VISIBLE_DEVICES"] = str(get_free_gpu())
print("Using GPU: {}".format(os.environ['CUDA_VISIBLE_DEVICES']))

continue_training = True
os.environ["OMP_NUM_THREADS"] = '4'
print(ARGS)

def detect_shadow(ambient, flashonly):
    intensity_ambient = tf.norm(ambient, axis=3, keepdims=True)
    intensity_flashonly = tf.norm(flashonly, axis=3, keepdims=True)
    ambient_ratio = intensity_ambient / tf.reduce_mean(intensity_ambient)
    flashonly_ratio = intensity_flashonly / tf.reduce_mean(intensity_flashonly)

    pf_div_by_ambient = flashonly_ratio / (ambient_ratio + 1e-5)
    shadow_mask = tf.cast(tf.less(pf_div_by_ambient, 0.8), tf.float32)

    dark_mask = tf.cast(tf.less(intensity_flashonly, 0.3), tf.float32)
    mask = dark_mask * shadow_mask
    return mask

with tfv1.variable_scope(tfv1.get_variable_scope()):
    input_ambient = tfv1.placeholder(tf.float32, shape=[None, None, None, 3])
    input_pureflash = tfv1.placeholder(tf.float32, shape=[None, None, None, 3])
    input_flash = tfv1.placeholder(tf.float32, shape=[None, None, None, 3])
    mask_shadow = tf.cast(tf.greater(input_pureflash, 0.02), tf.float32)
    mask_highlight = tf.cast(tf.less(input_flash, 0.96), tf.float32)
    mask_shadow_highlight = mask_shadow * mask_highlight
    gray_pureflash = 0.33 * (input_pureflash[..., 0:1] + input_pureflash[..., 1:2] + input_pureflash[..., 2:3])
    bad_mask = detect_shadow(input_ambient, input_pureflash)
    reflection_layer = UNet_SE(tf.concat([input_ambient, gray_pureflash, (-bad_mask + 1)], axis=3), output_channel=3, ext='Ref_')
    transmission_layer = UNet_SE(tf.concat([input_ambient, reflection_layer, (-bad_mask + 1)], axis=3), ext='Trans_')

saver = tfv1.train.Saver(max_to_keep=20)
config = tfv1.ConfigProto()
config.gpu_options.allow_growth = True
sess = tfv1.Session(config=config)
sess.run(tfv1.global_variables_initializer())
var_restore = [v for v in tfv1.trainable_variables()]
saver_restore = tfv1.train.Saver(var_restore)
ckpt = tfv1.train.get_checkpoint_state('./ckpt/' + model)

print("[i] contain checkpoint:", ckpt)
if ckpt and continue_training:
    saver_restore = tfv1.train.Saver([var for var in tfv1.trainable_variables()])
    print('loaded', ckpt.model_checkpoint_path)
    saver_restore.restore(sess, ckpt.model_checkpoint_path)

data_dir = "{}/others".format(ARGS.testset)
data_names = sorted(glob(data_dir + "/*ambient.jpg"))

def crop_shape(tmp_all, size=32):
    h, w = tmp_all.shape[1:3]
    h = h // size * size
    w = w // size * size
    return h, w

num_test = len(data_names)
print(num_test)
for epoch in range(9999, 10000):
    print("Processing epoch %d" % epoch, "./ckpt/%s/%s" % (model, data_dir.split("/")[-2]))
    save_dir = "./ckpt/%s/%s" % (model, data_dir.split("/")[-2])
    if not os.path.isdir(save_dir):
        os.makedirs(save_dir)

    print("output path: {}".format(save_dir))
    all_loss_test = np.zeros(num_test, dtype=float)
    metrics = {"T_ssim": 0, "T_psnr": 0, "R_ssim": 0, "R_psnr": 0}
    fetch_list = [transmission_layer, reflection_layer, input_ambient, input_flash, input_pureflash, bad_mask]
    for id in tqdm(range(num_test)):
        st = time.time()
        tmp_pureflash = imageio.imread(data_names[id].replace("ambient.jpg", "pureflash.jpg"))[None, ...] / 255.
        tmp_ambient = imageio.imread(data_names[id])[None, ...] / 255.
        tmp_flash = imageio.imread(data_names[id].replace("ambient.jpg", "flash.jpg"))[None, ...] / 255.
        h, w = crop_shape(tmp_ambient, size=32)
        tmp_ambient, tmp_pureflash, tmp_flash = tmp_ambient[:, :h, :w, :], tmp_pureflash[:, :h, :w, :], tmp_flash[:, :h, :w, :]
        pred_image_t, pred_image_r, in_ambient, in_flash, in_pureflash, pred_mask = sess.run(fetch_list,
                                                                                             feed_dict={input_ambient: tmp_ambient,
                                                                                                        input_pureflash: tmp_pureflash,
                                                                                                        input_flash: tmp_flash})
        save_path = "{}/{}".format(save_dir, data_names[id].split("/")[-1])
        imageio.imwrite(save_path.replace("ambient.jpg", "_0_input_ambient.png"), np.uint8(tmp_ambient[0].clip(0, 1) * 255.))
        imageio.imwrite(save_path.replace("ambient.jpg", "_1_pred_transmission.png"), np.uint8(pred_image_t[0].clip(0, 1) * 255.))
        imageio.imwrite(save_path.replace("ambient.jpg", "_3_input_flash.png"), np.uint8(tmp_flash[0].clip(0, 1) * 255.))
        imageio.imwrite(save_path.replace("ambient.jpg", "_4_input_pureflash.png"), np.uint8(tmp_pureflash[0].clip(0, 1) * 255.))
