import sys
import torch
import torch.nn as nn
import os

sys.path.insert(0, "../")



import torchvision.transforms.functional as TF
# print(os.path.abspath(os.getcwd()))
import numpy as np
from tqdm import tqdm
from tqdm.contrib import tzip
import torchvision
import torchvision.transforms as transforms
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.data import TensorDataset, DataLoader, Dataset

from utils.helper import cal_std_mean_and_get_plot_data, save_std_mean, plot_all_model, compute_mean_std

from models.base_model import Models
from models.gradient_dropconnect import GradWeightDrop as gd2
from torch.nn.modules.utils import _pair
import random
import matplotlib.pyplot as plt
from random import shuffle
from collections import OrderedDict
from torch.backends import cudnn

cudnn.benchmark = True # fast training

class LocallyConnected2d(nn.Module):
    def calculate_spatial_output_shape(self, input_shape, kernel_size, dilation, padding, stride):
        return [np.floor((self.input_shape[index] + 2 * self.padding[index] - self.dilation[index] * (self.kernel_size[index] - 1) - 1) / self.stride[index] + 1).astype(int) for index in range(2)]
    
    def __init__(self, input_shape, in_channels, out_channels, kernel_size=3, dilation=1, padding=1, stride=1):
        super().__init__()
        self.input_shape = _pair(input_shape)
        self.kernel_size = _pair(kernel_size)
        self.out_channels = out_channels
        self.dilation = _pair(dilation)
        self.padding = _pair(padding)
        self.stride = _pair(stride)
        
        self.output_height, self.output_width = self.calculate_spatial_output_shape(self.input_shape, kernel_size,
                                                                               dilation, padding, stride)
        self.weight_tensor_depth = in_channels * self.kernel_size[0] * self.kernel_size[1]
        self.spatial_blocks_size = self.output_height * self.output_width
        self.weight = nn.Parameter(torch.empty((1, self.weight_tensor_depth, self.spatial_blocks_size, out_channels),
                                   requires_grad=True, dtype=torch.float))
        self.bias = nn.Parameter(torch.empty((1, out_channels, self.output_height, self.output_width),
                                requires_grad=True, dtype=torch.float))
        
        nn.init.xavier_uniform_(self.weight)
        nn.init.xavier_uniform_(self.bias)
        
    def forward(self, input):
        input_unf = torch.nn.functional.unfold(input, self.kernel_size, dilation=self.dilation,
                                               padding=self.padding, stride=self.stride)
        local_conv_unf = (input_unf.view((*input_unf.shape, 1)) * self.weight)
        return local_conv_unf.sum(dim=1).transpose(2, 1).reshape(
                                        (-1, self.out_channels, self.output_height, self.output_width)) + self.bias  
        
        
class AlexNet(Models):
    def __init__(self, num_classes, add_layer=None, 
                 drop_model=None, drop_connect=False, apply_lr_scr=True, 
                 normal_drop=False, p=0.5, model_name="123"):
        super().__init__()

        self.model_name = model_name
        self.add_layer = add_layer
        self.drop_model = drop_model
        self.drop_connect = drop_connect
        self.normal_drop = normal_drop
        self.p = p    
        
        self.conv_layers = nn.Sequential(
                            nn.Conv2d(2, 96, kernel_size=11, padding=0, stride=4),
                            nn.ReLU(inplace=True),
                            nn.MaxPool2d(kernel_size=3, stride=2),
                            nn.Conv2d(96, 256, kernel_size=5, padding=2),
                            nn.ReLU(inplace=True),
                            nn.MaxPool2d(kernel_size=3, stride=2),
                            nn.Conv2d(256, 384, kernel_size=3, stride=1, padding=1),
                            nn.ReLU(inplace=True),
                            nn.Conv2d(384, 384, kernel_size=3, stride=1, padding=1),
                            nn.ReLU(inplace=True),
                            nn.Conv2d(384, 256, kernel_size=3, stride=1, padding=1),
                            nn.ReLU(inplace=True),
                            nn.MaxPool2d(kernel_size=3, stride=2),
                            )
        self.linear_total = nn.Sequential(OrderedDict([
            ('flatten', nn.Flatten()),
            ("linear1", nn.Linear(256*3*3, 4096)),
            ("ReLU1", nn.ReLU(inplace=True)),
            ("linear2", nn.Linear(4096, 4096)),
            ("ReLU2", nn.ReLU(inplace=True)),
            ("linear3", nn.Linear(4096, num_classes)),
        ]))
    def forward(self, x):
        x = self.conv_layers(x)
        x = self.linear_total(x)
        return x
    
class AlexNet_dropout(Models):
    def __init__(self, num_classes, add_layer=None, 
                 drop_model=None, drop_connect=False, apply_lr_scr=True, 
                 normal_drop=False, p=0.5, model_name="123"):
        super().__init__()
        
        self.model_name = model_name
        self.add_layer = add_layer
        self.drop_model = drop_model
        self.drop_connect = drop_connect
        self.normal_drop = normal_drop
        self.p = p    
        
        self.conv_layers = nn.Sequential(
                            nn.Conv2d(2, 96, kernel_size=11, padding=0, stride=4),
                            nn.ReLU(inplace=True),
                            nn.MaxPool2d(kernel_size=3, stride=2),
                            nn.Conv2d(96, 256, kernel_size=5, padding=2),
                            nn.ReLU(inplace=True),
                            nn.MaxPool2d(kernel_size=3, stride=2),
                            nn.Conv2d(256, 384, kernel_size=3, stride=1, padding=1),
                            nn.ReLU(inplace=True),
                            nn.Conv2d(384, 384, kernel_size=3, stride=1, padding=1),
                            nn.ReLU(inplace=True),
                            nn.Conv2d(384, 256, kernel_size=3, stride=1, padding=1),
                            nn.ReLU(inplace=True),
                            nn.MaxPool2d(kernel_size=3, stride=2),
                            )
        self.linear_total = nn.Sequential(OrderedDict([
            ('flatten', nn.Flatten()),
            ("linear1", nn.Linear(256*3*3, 4096)),
            ("ReLU1", nn.ReLU(inplace=True)),
            ("Dropout1", nn.Dropout(p=p)),
            ("linear2", nn.Linear(4096, 4096)),
            ("ReLU2", nn.ReLU(inplace=True)),
            ("linear3", nn.Linear(4096, num_classes)),
        ]))

    def forward(self, x):
        x = self.conv_layers(x)
        x = self.linear_total(x)
        return x