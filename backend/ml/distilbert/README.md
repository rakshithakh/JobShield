`config.json` is a DistilBERT architecture config from the original repository. **No tokenizer or fine-tuned weights exist
in this repo**, so the DistilBERT path cannot run. To enable it: fine-tune a `DistilBertForSequenceClassification` (label 1 = scam)
on a real labelled dataset, save it with `save_pretrained`, install `requirements-ml-optional.txt`, and set `DISTILBERT_MODEL_DIR`.
