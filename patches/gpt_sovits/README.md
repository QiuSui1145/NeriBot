# GPT-SoVITS 补丁说明

本目录包含为 QQ 机器人音理 (Kazamata Neri) 定制的 GPT-SoVITS 服务端修改文件。

## 文件清单
- `api_v2.py`: 增强版推理 API 接口
  - ✨ 增加前端跨域支持 (`Access-Control-Allow-Origin: *`)
  - ✨ 增加致命异常拦截护航机制，避免 PyTorch 崩溃直接静默挂掉
  - ✨ 默认支持音频分段及模型热切换接口 (`/set_refer_audio`, `/set_gpt_weights`, `/set_sovits_weights`)
- `ref_audio/ner0092.wav`: 音理官方标定参考音频

## 安装方式
1. 可在 WebUI 的【TTS 语音设置】页面中直接输入 GPT-SoVITS 根目录，点击【安装补丁】一键完成。
2. 或手动将 `api_v2.py` 覆盖复制到您的 `GPT-SoVITS` 根目录下即可。
