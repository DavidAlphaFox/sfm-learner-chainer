#/usr/bin/env python3
# -*- coding: utf-8 -*-

from functools import partial
import time

import cv2 as cv
import numpy as np
from PIL import Image
import copy

from chainer import datasets
from datasets.kitti.kitti_raw_dataset import KittiRawDataset

def make_intrinsics_matrix(fx, fy, cx, cy):
    # Assumes batch input
    batch_size = fx.get_shape().as_list()[0]
    zeros = tf.zeros_like(fx)
    r1 = tf.stack([fx, zeros, cx], axis=1)
    r2 = tf.stack([zeros, fy, cy], axis=1)
    r3 = tf.constant([0.,0.,1.], shape=[1, 3])
    r3 = tf.tile(r3, [batch_size, 1])
    intrinsics = tf.stack([r1, r2, r3], axis=1)
    return intrinsics

def data_augmentation(tgt_img, src_imgs, intrinsics):
    """Data augmentation for training models.

       Args:
           tgt_img(ndarray): Shape is (3, H, W)
           src_img(list): Shape is [N, 3, H, W]
           intrinsics(ndarray): Shape is (3, 3)
    """
    # Random scaling
    def random_scaling(im, intrinsics):
        batch_size, in_h, in_w, _ = im.get_shape().as_list()
        scaling = np.random.uniform(1, 1.15, 2)
        x_scaling = scaling[0]
        y_scaling = scaling[1]
        out_h = tf.cast(in_h * y_scaling, dtype=tf.int32)
        out_w = tf.cast(in_w * x_scaling, dtype=tf.int32)
        im = tf.image.resize_area(im, [out_h, out_w])
        fx = intrinsics[:,0,0] * x_scaling
        fy = intrinsics[:,1,1] * y_scaling
        cx = intrinsics[:,0,2] * x_scaling
        cy = intrinsics[:,1,2] * y_scaling
        intrinsics = make_intrinsics_matrix(fx, fy, cx, cy)
        return im, intrinsics

    # Random cropping
    def random_cropping(im, intrinsics, out_h, out_w):
        # batch_size, in_h, in_w, _ = im.get_shape().as_list()
        batch_size, in_h, in_w, _ = tf.unstack(tf.shape(im))
        offset_y = tf.random_uniform([1], 0, in_h - out_h + 1, dtype=tf.int32)[0]
        offset_x = tf.random_uniform([1], 0, in_w - out_w + 1, dtype=tf.int32)[0]
        im = tf.image.crop_to_bounding_box(
            im, offset_y, offset_x, out_h, out_w)
        fx = intrinsics[:,0,0]
        fy = intrinsics[:,1,1]
        cx = intrinsics[:,0,2] - tf.cast(offset_x, dtype=tf.float32)
        cy = intrinsics[:,1,2] - tf.cast(offset_y, dtype=tf.float32)
        intrinsics = make_intrinsics_matrix(fx, fy, cx, cy)
        return im, intrinsics

    _, out_h, out_w = tgt_img.shape
    im, intrinsics = random_scaling(im, intrinsics)
    im, intrinsics = random_cropping(im, intrinsics, out_h, out_w)
    im = tf.cast(im, dtype=tf.uint8)
    return im, intrinsics

def get_multi_scale_intrinsics(intrinsics, n_scales):
    """Scale the intrinsics accordingly for each scale
       Args:
           intrinsics: Intrinsics for original image. Shape is (3, 3).
           n_scales(int): Number of scale.
       Returns:
           multi_intrinsics: Multi scale intrinsics.
    """
    multi_intrinsics = []
    for s in range(n_scales):
        fx = intrinsics[0, 0]/(2 ** s)
        fy = intrinsics[1, 1]/(2 ** s)
        cx = intrinsics[0, 2]/(2 ** s)
        cy = intrinsics[1, 2]/(2 ** s)
        intrinsics = np.array([[fx, 0., cx],
                               [0., fy, cy],
                               [0., 0., 1.]])
        multi_intrinsics.append(intrinsics)
    return multi_intrinsics

def _transform(inputs, n_scale=4, ):
    tgt_img, reg_imgs, intrinsics, inv_intrinsics = inputs
    del inputs

    # # Global scaling
    # if g_scale:
    #     scale = np.random.uniform(g_scale[0], g_scale[1], 4)
    #     pc *= scale
    #     places *= scale[:3]
    #     size *= scale[:3]

    # # Flip
    # if fliplr:
    #     if np.random.rand() > 0.5:
    #         pc[:, 1] = pc[:, 1] * -1
    #         places[:, 1] = places[:, 1] * -1
    #         rotates = rotates * -1

    tgt_img, src_imgs, intrinsics = data_augmentation(tgt_img, src_imgs,
                                                      intrinsics)
    intrinsics = get_multi_scale_intrinsics(intrinsics, n_scale)
    return tgt_img, src_imgs, intrinsics, _


class KittiRawTransformed(datasets.TransformDataset):
    def __init__(self, data_dir=None, seq_len=3, split='train',
                 n_scale=4, ):
        self.d = KittiRawDataset(
            data_dir=None, seq_len=3, split='train')
        t = partial(
            _transform, n_scale=4, )
        super().__init__(self.d, t)
