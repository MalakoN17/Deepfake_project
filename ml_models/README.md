# Pre-trained models

All models run on the CPU through OpenCV's DNN module (`cv2.dnn`) - no PyTorch, TensorFlow or GPU.

| File | Purpose | Source | License |
| --- | --- | --- | --- |
| `meso4_df.onnx` | Deepfake detection (probability that a face is real) | MesoNet Meso4, weights `Meso4_DF.h5` from [DariusAf/MesoNet](https://github.com/DariusAf/MesoNet), converted with `scripts/convert_mesonet.py` | Apache-2.0 |
| `face_detector.prototxt` + `face_detector.caffemodel` | Face detection (ResNet-10 SSD, 300x300) | [OpenCV samples](https://github.com/opencv/opencv/tree/4.x/samples/dnn/face_detector) / [opencv_3rdparty](https://github.com/opencv/opencv_3rdparty/tree/dnn_samples_face_detector_20180205_fp16) | BSD / Apache-2.0 (OpenCV) |
| `openface_nn4.small2.v1.t7` | 128-d face embeddings for identity verification | [OpenFace](https://cmusatyalab.github.io/openface/) nn4.small2.v1 | Apache-2.0 |

Paper for the deepfake model: Afchar, D., Nozick, V., Yamagishi, J., & Echizen, I. (2018).
*MesoNet: a Compact Facial Video Forgery Detection Network*. IEEE WIFS 2018.

The ONNX conversion was verified against an independent NumPy implementation of the
original Keras network (maximum difference < 1e-6).

## Replacing the deepfake model

Any model can be plugged in by adding a class with `name` and `predict(face_bgr_256) -> probability_of_fake`
to `app/services/detector.py` and selecting it in `load_detector()`. A stronger model
(e.g. EfficientNet-B4 or Xception trained on FaceForensics++) exported to ONNX would be the
natural upgrade - at the cost of more CPU time per frame.

If the model files are missing, run `python scripts/download_models.py`.
