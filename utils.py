import numpy as np 
from keras.preprocessing.sequence import pad_sequences 
import logging
import json 
import random
import torch
import os
from typing import * 

logger = logging.getLogger(__file__)

YESAND_DATAPATH = 'data/yes-and-data.json'
MAX_LEN = 128
ROBERTA_MAX_LEN = 512

def calc_metrics(pred, labels): 
    """Function to calculate the accuracy of predictions vs labels """
    pred_flat = np.argmax(pred, axis = 1).flatten()
    labels_flat = labels.flatten()
  
    flat_accuracy = np.sum(pred_flat == labels_flat) / len(labels_flat)
  
    # sklearn takes first parameter as the true label
    precision = precision_score(labels_flat, pred_flat)
    recall = recall_score(labels_flat, pred_flat)
  
    return flat_accuracy, precision, recall

def calc_f1(pred,labels): 
    pred_flat = np.argmax(pred, axis = 1).flatten()
    labels_flat = labels.flatten()
  
    # f1_score from sklearn.metrics take first parameter as the true label
    return f1_score(labels_flat, pred_flat)

def build_segment_ids(input_ids):
    """ Create segment ids to differentiate sentence1 and sentence2 """ 
    segment_ids = [] 
    for seq in input_ids: 
        segment_id = []
        id_ = 0
        for token_id in seq: 
            segment_id.append(id_)
            # 102 : [SEP]
            if token_id == 102: 
                id_ +=1 
                id_ %= 2 
        segment_ids.append(segment_id)
    return segment_ids 

def build_attention_mask(input_ids): 

    """ Create attention masks to differentiate from valid input and pads""" 
    attention_masks = [] 

    # 1 for input and 0 for pad
    for seq in input_ids: 
        attention_masks.append([float(i>0) for i in seq])

    return attention_masks 


# TODO: Adjust this function for loading your data 
def get_data(data_path=None):

    data_path = data_path or YESAND_DATAPATH

    logger.info("Loading data from: {}".format(data_path))
    with open(data_path, 'r') as f: 
        data = json.load(f) 
    logger.info("Loaded data from: {}".format(data_path))

    # # make sure data set is balanced
    # total_yes_ands = 0
    # for k in data['yes-and'].keys(): 
    #     total_yes_ands += len(data['yes-and'][k])
    
    # logger.info("Total number of yes-ands: {}".format(total_yes_ands))

    return data 

def get_roberta_inputs(seq1: str, seq2:str, tokenizer: object): 
    # input_ids: tokenize input and prepare them into correct format
    # token_type_ids: ids that differentiate seq1 and seq2
    # attention_mask: identify padding 

    seq1 = tokenizer.encode(seq1)
    seq2 = tokenizer.encode(seq2)
    input_ids = tokenizer.build_inputs_with_special_tokens(seq1, seq2)
    input_ids += [tokenizer.pad_token_id] * (ROBERTA_MAX_LEN - len(input_ids)) #pad

    token_type_ids = tokenizer.create_token_type_ids_from_sequences(seq1, seq2) 
    token_type_ids += [tokenizer.pad_token_id] * (ROBERTA_MAX_LEN - len(token_type_ids)) #pad

    attention_mask = [float(i!=tokenizer.pad_token_id) for i in input_ids] #attention mask 

    assert len(input_ids) == len(token_type_ids) == len(attention_mask) == ROBERTA_MAX_LEN

    return input_ids, token_type_ids, attention_mask 


def build_roberta_input(data: str, data_path: str, tokenizer: object): 
    # Build robert input from yes-and data or load from cache 

    # cache name identified by tokenizer's name so that cache files created with different tokenizers are differentiated
    cache_fp = data_path[:data_path.rfind('.')] + "_" + type(tokenizer).__name__
    if os.path.isfile(cache_fp): 
        logger.info("Loading tokenized data from cache...")
        all_samples = torch.load(cache_fp)
        return all_samples

    logger.info("Preparing and tokenizing yes-and data...")
    all_samples = [] 
    for k in data['non-yes-and'].keys():
        for non_yesand in data['non-yes-and'][k]: 
            input_ids, token_type_ids, attention_mask = get_roberta_inputs(non_yesand['prompt'], non_yesand['response'], tokenizer)
            all_samples.append({"input_ids": input_ids, "token_type_ids": token_type_ids, "attention_mask": attention_mask, "label": 0})

    for k in data['yes-and'].keys(): 
        for yesand in data['yes-and'][k]: 
            input_ids, token_type_ids, attention_mask = get_roberta_inputs(yesand['prompt'], yesand['response'], tokenizer)
            all_samples.append({"input_ids": input_ids, "token_type_ids": token_type_ids, "attention_mask": attention_mask, "label": 1})

    
    torch.save(all_samples, cache_fp)

    return all_samples 



# TODO: Adjust this function for formatting your data 
## There may be some issues with the saving and loading process of cache files
## Tokenized text and labels may not align 
def build_bert_input(data, data_path, tokenizer): 

    """
    Format data as BERT input 
    sequence: "[CLS] <sentence1> [SEP] <sentence2> [SEP]"
    """

    all_samples = [] 
    for non_yesand in data['non-yes-and']['cornell']: 
        seq = "[CLS] {} [SEP] {} [SEP]".format(non_yesand['prompt'], non_yesand['response'])
        all_samples.append([0, seq])
    
    for k in data['yes-and'].keys(): 
        for yesand in data['yes-and'][k]: 
            seq = "[CLS] {} [SEP] {} [SEP]".format(yesand['prompt'], yesand['response'])
            all_samples.append([1, seq])
        
    random.shuffle(all_samples)

    sentences = [x[1] for x in all_samples]
    labels = [x[0] for x in all_samples]

    cache_fp = data_path[:data_path.rfind('.')] + "_" + type(tokenizer).__name__
    if os.path.isfile(cache_fp): 
        logger.info("Loading tokenized data from cache...")
        tokenized_texts = torch.load(cache_fp)
    else: 
        logger.info("Tokenizing loaded data...")
        # tokenize with BERT tokenizer 
        tokenized_texts = [tokenizer.encode(sentence) for sentence in sentences]
        torch.save(tokenized_texts, cache_fp)

    # pad input to MAX_LEN
    input_ids = pad_sequences(tokenized_texts, maxlen=MAX_LEN, dtype="long", truncating="post", padding="post")

    # get attention masks and segment ids 
    attention_masks = build_attention_mask(input_ids)
    segment_ids = build_segment_ids(input_ids)

    return input_ids, attention_masks, segment_ids, labels


