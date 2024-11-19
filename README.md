# Image Captioning Model


**Image Captioning** is a deep learning project that combines Vision Transformer (ViT) and GPT-2 to generate descriptive captions for images. The model effectively integrates computer vision and natural language processing to create meaningful image descriptions.

### 🚀 Features

- **Image Feature Extraction**: Utilizes Vision Transformer (ViT) for high-quality image feature extraction.
- **Text Generation**: Leverages GPT-2 to produce fluent and contextually accurate captions.
- **Seamless Integration**: Combines computer vision and NLP for enhanced performance in image captioning tasks.

### 🛠️ Technologies Used

- **Frameworks**: PyTorch
- **Models**: Vision Transformer (ViT), GPT-2
- **Languages**: Python

### Dataset

The dataset I used was `COCO 2017` with options for `Flickr30k` and `Flickr8k`.

- The dataset preparation was also done from scratch
- my code goes in detail about how to prepare the labels for causal language modeling, calculating the loss while ignoring special tokens, etc.
- Dynamic padding with custom collate function to pad sequences based on the batch and not the max length of the model.


### Training

- The training loop was written from scratch, the metric I used was `perplexity = e^loss`
- I trained it with mixed-precision fp16 using `torch.amp`.
- I initially trained the randomly initialized cross-attention layers, then in further  epochs, I finetuned the entire GPT2 and in further epochs I finetuned the entire ViT-GPT2 model.

### Generation

- Standard `torch.multinomial` sampling based generation with temperature control.
- Support for deterministic generation with `torch.argmax`
- The results are good not great, I only trained on about 30% of the training samples in COCO.

### Results

| Epoch | Train Loss | Train Perplexity | Val Loss | Val Perplexity |
|---|---|---|---|---|
| 0 | 5.164732 | 174.990611 | 3.288565 | 26.804375 |
| 1 | 2.668888 | 14.423919 | 2.341017 | 10.391795 |
| 2 | 2.30841 | 10.058415 | 2.201064 | 9.034617 |
| 3 | 2.033982 | 7.64447 | 2.099659 | 8.163385 |
| 4 | 1.855595 | 6.395501 | 2.08667 | 8.058035 |
