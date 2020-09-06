import torch.nn as nn
from transformers import BertModel

PRETRAINED_MODEL = 'bert-base-cased'


class BertSentimentClassifier(nn.Module):
    def __init__(self, n_classes):
        super(BertSentimentClassifier, self).__init__()
        self.bert = BertModel.from_pretrained(PRETRAINED_MODEL)
        self.dropout = nn.Dropout(p=0.2)
        self.out_linear = nn.Linear(self.bert.config.hidden_size, n_classes)
        self.softmax = nn.Softmax(dim=1)

    def forward(self, input_ids, attention_mask):
        _, pooled_out = self.bert(
            input_ids=input_ids,
            attention_mask=attention_mask
        )
        out = self.dropout(pooled_out)
        out = self.out_linear(out)
        return self.softmax(out)