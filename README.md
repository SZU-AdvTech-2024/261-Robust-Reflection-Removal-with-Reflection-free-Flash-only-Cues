## 简要快速开始

要设置一个 conda 环境并在演示数据上进行测试：

复制

```bash
conda env create -f environment.yml
conda activate flashrr-rfc
bash download.sh
python test.py
```

## 设置

### 环境

安装 conda 后，您可以通过以下命令轻松设置环境：

复制

```bash
conda env create -f environment.yml
```

### 下载检查点和 VGG 模型

您可以通过以下命令下载 ckpt 和 VGG 模型：

复制

```bash
bash download.sh
```

## 快速推理

您可以通过以下命令获取演示数据的结果：

复制

```bash
python test.py
```

如果您准备了自己的数据集，请注意每个数据样本必须包含一张环境光图像和一张仅闪光灯图像：

复制

```bash
python test.py --testset /path/to/your/testset
```

## 训练

### 复现结果

首先，下载数据集：

复制

```bash
bash download_data.sh
```

然后，您可以通过以下命令训练模型：

复制

```bash
python my_train.py --model YOUR_MODEL_NAME
```
