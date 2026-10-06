from __future__ import annotations
"""
Convert the original MesoNet (Meso4) Keras weights (.h5) into an ONNX file
that OpenCV's DNN module can run - so the server needs no TensorFlow/PyTorch.

Source weights: https://github.com/DariusAf/MesoNet (Apache-2.0)
Paper: Afchar et al., "MesoNet: a Compact Facial Video Forgery Detection Network", WIFS 2018.

Dev-only dependencies:  pip install h5py onnx
Usage:  python scripts/convert_mesonet.py weights/Meso4_DF.h5 ml_models/meso4_df.onnx
"""
import sys

import h5py
import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

EPS = 1e-3  # Keras BatchNormalization default epsilon


def load_weights(path):
    f = h5py.File(path, "r")
    get = lambda layer, name: np.array(f[f"{layer}/{layer}/{name}:0"])
    convs = [f"conv2d_{i}" for i in range(5, 9)]
    bns = [f"batch_normalization_{i}" for i in range(5, 9)]
    return f, get, convs, bns


def convert(src, dst):
    f, get, convs, bns = load_weights(src)
    nodes, inits = [], []
    x = "input"  # NCHW, float32, RGB, values in [0, 1], 256x256
    pools = [2, 2, 2, 4]
    for i, (conv, bn) in enumerate(zip(convs, bns)):
        k = get(conv, "kernel")                     # (kh, kw, in, out)  Keras
        w = np.transpose(k, (3, 2, 0, 1)).copy()    # (out, in, kh, kw)  ONNX
        pad = k.shape[0] // 2
        inits += [numpy_helper.from_array(w.astype(np.float32), f"w{i}"),
                  numpy_helper.from_array(get(conv, "bias").astype(np.float32), f"b{i}")]
        nodes.append(helper.make_node("Conv", [x, f"w{i}", f"b{i}"], [f"c{i}"],
                                      kernel_shape=list(k.shape[:2]), pads=[pad] * 4))
        nodes.append(helper.make_node("Relu", [f"c{i}"], [f"r{i}"]))
        for n in ("gamma", "beta", "moving_mean", "moving_variance"):
            inits.append(numpy_helper.from_array(get(bn, n).astype(np.float32), f"{n}{i}"))
        nodes.append(helper.make_node("BatchNormalization",
                                      [f"r{i}", f"gamma{i}", f"beta{i}", f"moving_mean{i}", f"moving_variance{i}"],
                                      [f"n{i}"], epsilon=EPS))
        p = pools[i]
        nodes.append(helper.make_node("MaxPool", [f"n{i}"], [f"p{i}"], kernel_shape=[p, p], strides=[p, p]))
        x = f"p{i}"
    # Keras flattens NHWC (8x8x16) -> reorder Dense rows to match ONNX NCHW flatten
    d1 = get("dense_3", "kernel").reshape(8, 8, 16, 16).transpose(2, 0, 1, 3).reshape(1024, 16)
    inits += [numpy_helper.from_array(d1.astype(np.float32), "d1w"),
              numpy_helper.from_array(get("dense_3", "bias").astype(np.float32), "d1b"),
              numpy_helper.from_array(get("dense_4", "kernel").astype(np.float32), "d2w"),
              numpy_helper.from_array(get("dense_4", "bias").astype(np.float32), "d2b")]
    nodes += [helper.make_node("Flatten", [x], ["flat"], axis=1),
              helper.make_node("Gemm", ["flat", "d1w", "d1b"], ["g1"]),
              helper.make_node("LeakyRelu", ["g1"], ["l1"], alpha=0.1),
              helper.make_node("Gemm", ["l1", "d2w", "d2b"], ["g2"]),
              helper.make_node("Sigmoid", ["g2"], ["prob_real"])]
    graph = helper.make_graph(nodes, "meso4",
                              [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, 256, 256])],
                              [helper.make_tensor_value_info("prob_real", TensorProto.FLOAT, [1, 1])], inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 11)])
    model.ir_version = 7
    onnx.checker.check_model(model)
    onnx.save(model, dst)
    print(f"Saved {dst}  (output = probability that the face is REAL)")


if __name__ == "__main__":
    convert(sys.argv[1], sys.argv[2])
