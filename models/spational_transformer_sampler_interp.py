import numpy

import chainer
from chainer import function
from chainer.utils import argument
from chainer.utils import type_check
from chainer import cuda

class SpatialTransformerSamplerInterp(function.Function):

    def check_type_forward(self, in_types):
        n_in = in_types.size()
        type_check.expect(2 == n_in)

        x_type = in_types[0]
        grid_type = in_types[1]
        type_check.expect(
            x_type.dtype.char == 'f',
            grid_type.dtype.char == 'f',
            x_type.ndim == 4,
            grid_type.ndim == 4,
            grid_type.shape[1] == 2,
            x_type.shape[0] == grid_type.shape[0],
        )

    def forward_cpu(self, inputs):
        return self._forward(inputs)

    def forward_gpu(self, inputs):
        return self._forward(inputs)

    def _forward(self, inputs):
        x, grid = inputs
        xp = cuda.get_array_module(x)
        B, C, H, W = x.shape
        _, _, out_H, out_W = grid.shape

        u = grid[:, 0].reshape(-1)
        v = grid[:, 1].reshape(-1)

        u0 = xp.floor(u)
        u1 = u0 + 1
        v0 = xp.floor(v)
        v1 = v0 + 1

        u0 = u0.clip(0, W - 1)
        v0 = v0.clip(0, H - 1)
        u1 = u1.clip(0, W - 1)
        v1 = v1.clip(0, H - 1)

        # weights
        wt_x0 = u1 - u
        wt_x1 = u - u0
        wt_y0 = v1 - v
        wt_y1 = v - v0

        w1 = wt_x0 * wt_y0
        w2 = wt_x1 * wt_y0
        w3 = wt_x0 * wt_y1
        w4 = wt_x1 * wt_y1
        w1 = w1.astype(x.dtype)
        w2 = w2.astype(x.dtype)
        w3 = w3.astype(x.dtype)
        w4 = w4.astype(x.dtype)

        u0 = u0.astype(numpy.int32)
        v0 = v0.astype(numpy.int32)
        u1 = u1.astype(numpy.int32)
        v1 = v1.astype(numpy.int32)

        batch_index = xp.repeat(xp.arange(B), out_H * out_W)
        y = w1[:, None] * x[batch_index, :, v0, u0]
        y += w2[:, None] * x[batch_index, :, v0, u1]
        y += w3[:, None] * x[batch_index, :, v1, u0]
        y += w4[:, None] * x[batch_index, :, v1, u1]

        y = y.reshape(B, out_H, out_W, C).transpose(0, 3, 1, 2)
        return y,

    def backward_cpu(self, inputs, grad_outputs):
        return self._backward(inputs, grad_outputs)

    def backward_gpu(self, inputs, grad_outputs):
        return self._backward(inputs, grad_outputs)

    def _backward(self, inputs, grad_outputs):
        x, grid = inputs
        xp = cuda.get_array_module(x)
        gy, = grad_outputs
        B, C, H, W = x.shape
        _, _, out_H, out_W = grid.shape

        u = grid[:, 0].reshape(-1)
        v = grid[:, 1].reshape(-1)

        # indices of the 2x2 pixel neighborhood surrounding the coordinates
        u0 = xp.floor(u)
        u1 = u0 + 1
        v0 = xp.floor(v)
        v1 = v0 + 1

        u0 = u0.clip(0, W - 1)
        v0 = v0.clip(0, H - 1)
        u1 = u1.clip(0, W - 1)
        v1 = v1.clip(0, H - 1)

        # weights
        wt_x0 = u1 - u
        wt_x1 = u - u0
        wt_y0 = v1 - v
        wt_y1 = v - v0

        wt_x0 = wt_x0.astype(gy.dtype)
        wt_x1 = wt_x1.astype(gy.dtype)
        wt_y0 = wt_y0.astype(gy.dtype)
        wt_y1 = wt_y1.astype(gy.dtype)

        u0 = u0.astype(numpy.int32)
        v0 = v0.astype(numpy.int32)
        u1 = u1.astype(numpy.int32)
        v1 = v1.astype(numpy.int32)

        batch_index = xp.repeat(xp.arange(B), out_H * out_W)
        x_indexed_1 = x[batch_index, :, v0, u0]
        x_indexed_2 = x[batch_index, :, v0, u1]
        x_indexed_3 = x[batch_index, :, v1, u0]
        x_indexed_4 = x[batch_index, :, v1, u1]

        gu = -wt_y0[:, None] * x_indexed_1
        gu += wt_y0[:, None] * x_indexed_2
        gu -= wt_y1[:, None] * x_indexed_3
        gu += wt_y1[:, None] * x_indexed_4

        gv = -wt_x0[:, None] * x_indexed_1
        gv -= wt_x1[:, None] * x_indexed_2
        gv += wt_x0[:, None] * x_indexed_3
        gv += wt_x1[:, None] * x_indexed_4

        gu = gu.reshape(B, out_H, out_W, C).transpose(0, 3, 1, 2)
        gv = gv.reshape(B, out_H, out_W, C).transpose(0, 3, 1, 2)

        gu *= gy
        gv *= gy
        gu = xp.sum(gu, axis=1)
        gv = xp.sum(gv, axis=1)
        # Offsets scaling of the coordinates and clip gradients.
        ggrid = xp.concatenate((gu[:, None], gv[:, None]), axis=1)
        gx = xp.zeros_like(x)
        return gx, ggrid


def spatial_transformer_sampler_interp(x, grid, **kwargs):
    argument.check_unexpected_kwargs(
        kwargs, use_cudnn="The argument \"use_cudnn\" is not "
        "supported anymore. "
        "Use chainer.using_config('use_cudnn', value) "
        "context where value can be `always`, `never`, or `auto`.")
    argument.assert_kwargs_empty(kwargs)
    return SpatialTransformerSamplerInterp()(x, grid)
