import addict
import yaml
import numpy as np

def get_data_from_yaml(filename):
    with open(filename, 'r') as stream:
        data = yaml.safe_load(stream)
    data = addict.Dict(data)
    return data

def get_data_from_txt(filename):#labels is an array of labels with fields: class, x, y, w, h, conf 
    labels = np.zeros((1,6))
    with open(filename, 'r') as f:
        for i, line in enumerate(f):
            if i == 0:
                labels[i] = [float(x) for x in line.split()]
            else:
                labels = np.vstack([labels, [float(x) for x in line.split()]])
    return labels