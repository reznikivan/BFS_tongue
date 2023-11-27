import cv2
import numpy as np
import time
import os
import addict
import yaml
import pybboxes as pbx
import copy
from config_util import get_data_from_txt

CONFIGFILE = "config.yaml"


def get_data_from_yaml(filename):
    with open(filename, 'r') as stream:
        data = yaml.safe_load(stream)
    data = addict.Dict(data)
    return data

def transform_to_grayscale(img):
    _, img = cv2.threshold(img, 1, 255, cv2.THRESH_BINARY)
    return img

def is_path(elem):
    res = (elem == config_data.not_path_point)
    if not np.isscalar(res):
        res_shape = res.shape[0] 
        if (res_shape > 1):
            res = False
            for i in range (res_shape):
                if elem[i] != config_data.not_path_point[i]:
                    res = True
                    break
    return res

def update_wide(cluster, row, mask, w):
    new_cluster = set([])
    for p in cluster:
        i = 1
        while p + i < w and is_path(mask[row, p + i]) and not p + i in cluster:
            new_cluster.add(p + i)
            i += 1
        i = 1
        while p - i >= 0 and is_path(mask[row, p - i]) and not p - i in cluster:
            new_cluster.add(p - i)
            i += 1       
    return cluster | new_cluster

def dist(c1, c2):
    dist = 10000
    for p1 in c1:
        for p2 in c2:
            if abs(p1 - p2) < dist:
                dist = abs(p1 - p2)
    return dist

def merge(clusters):
    i = 0
    while i < len(clusters):
        j = i + 1
        while i < j and j < len(clusters) and j >= 0 and i >= 0:
            if dist(clusters[i], clusters[j]) <= 1:
                res_cluster = clusters[i] | clusters[j]
                clusters.pop(i)
                clusters.pop(j - 1)
                clusters.append(res_cluster)
                i -= 1
                j -= 1
            j += 1
        i += 1
    if len(clusters) == 2 and dist(clusters[0], clusters[1]) <= 1:
        clusters[0] = clusters[0] | clusters[1]
        clusters.pop(1)
    return clusters

def update_up(clusters, row, mask):
    up_clusters = []
    for cluster in clusters[row]:
        for p in cluster:
            if row >= 1:
                if is_path(mask[row - 1, p]):
                    up_clusters.append(set([p]))
    if len(up_clusters) > 0:
        clusters[row - 1] = merge(up_clusters)
    return clusters

def not_in_all(clusters, p):
    res = True
    for cluster in clusters:
        if p in cluster:
            res = False
            break
    return res

def update_down(clusters, row, start_y, mask):
    down_clusters = []
    for cluster in clusters[row]:
        for p in cluster:
            if row <= start_y - 1:
                if is_path(mask[row + 1, p]) and not_in_all(clusters[row + 1], p):
                    down_clusters.append(set([p]))
    if len(down_clusters) > 0:
        clusters[row + 1] += merge(down_clusters)
    return clusters

def center(cluster):
    summ = 0
    for p in cluster:
        summ += p
    return int (summ / len(cluster))

def draw_clusters(image, clusters, start_y, end_y):
    res = image
    for row in range (end_y, start_y + 1):
        for cluster in clusters[row]:
            center_p = center(cluster)
            res = cv2.circle(res, [center_p, row], config_data.radius, [255, 0, 0], config_data.thickness)
    return res

def get_closest_tongue(labels, init_labels, clusters, mask):#get the closest to the train tongue
    labels = sorted(labels, key = lambda x:x[1], reverse = True)
    init_labels = sorted(init_labels, key = lambda x:x[2], reverse = True)#elem of init_labels is (class, x, y, w, h, conf) 
    while len(labels) > 0:
        if not get_down_to_start(labels[0], clusters, mask):# if we can't reach closest tongue
            labels = labels[1:]
            init_labels = init_labels[1:]
        else:
            break
    if len(labels) == 0:
        return labels, True, False
    else:
        if int(init_labels[0][0]) == 6:#if it's a down right tongue
            return labels[0], False, True
        return labels[0], True, True

def center_label(label):
    return ((label[0] + label[2]) // 2, (label[1] + label[3]) // 2)

def find_current_cluster(label, clusters):
    min_dist = 10000
    num = 0
    for i, cl in enumerate(clusters[center_label(label)[1]]):
        d = dist({center_label(label)[0]}, cl)
        if d < min_dist:
            min_dist = d
            num = i
    return num

def find_splitted_paths(row, split, clusters):#TODO: change finding of main path 
    num1, num2 = (0, 0)
    dists = dict()
    for i, cl in enumerate(clusters[row]):
        dists[i] = dist({split}, cl)
    dists = sorted(dists.items(), key = lambda x: x[1])
    num1, num2 = (dists[0][0], dists[1][0])
    start_cl = find_current_cluster((int(config_data.start[0] * config_data.size[0]), config_data.size[1] - 1, int(config_data.start[0] * config_data.size[0]), config_data.size[1] - 1), clusters)
    if abs(center(clusters[row][num2]) - center(clusters[-1][start_cl])) < abs(center(clusters[row][num1]) - center(clusters[-1][start_cl])):
        num1, num2 = num2, num1
    return (num1, num2)

def define_main_path_left(label, cl, clusters, res):#define wheter main path is left leading to the tongue
    ans = True
    #num_of_clusters = len(clusters[center_label(label)[1]])
    cur_center = center(clusters[center_label(label)[1]][cl])
    for i in range(center_label(label)[1], config_data.size[1]):
        cv2.circle(res, (cur_center, i), 5, color = (128, 128, 128), thickness = -1)
        #cv2.imshow('res', res)
        #cv2.waitKey(0)
        cur_cl = find_current_cluster((cur_center, i, cur_center, i), clusters) #find a number of the current cluster if we're within it
        if abs(cur_center - center(clusters[i][cur_cl])) > 8:
            #cv2.imshow('path', res)
            #cv2.waitKey(0)
            main_cl, side_cl = find_splitted_paths(i, cur_center, clusters)
            last_row = i
            break
        else:
            cur_center = center(clusters[i][cur_cl])
    if center(clusters[last_row][main_cl]) > center(clusters[last_row][side_cl]):#cl1 is less number than cl2, which means we came from cl1
        ans = False #cl1 is right
    return ans

def get_down_to_start(label, clusters, mask):
    i = center_label(label)[1]
    cl = find_current_cluster(label, clusters)
    cur_center = center(clusters[center_label(label)[1]][cl])
    cur_cl = cl
    prev_len_cl = len(clusters[i])
    while i < config_data.size[1] and abs(cur_center) >= 0 and cur_center < config_data.size[0] and is_path(mask[i, cur_center]):
        cur_cl = find_current_cluster((cur_center, i, cur_center, i), clusters) #find a number of the current cluster if we're within it
        if abs(cur_center - center(clusters[i][cur_cl])) > 8:
            if len(clusters[i]) > prev_len_cl:
                main_cl, _ = find_splitted_paths(i, cur_center, clusters)
            else:
                main_cl = cur_cl#means we're on a UR or UL tongue and already jumped on the right cluster
            cur_center = center(clusters[i][main_cl])
        else:
            cur_center = center(clusters[i][cur_cl])#TODO: check whhy algo goes till the end of frame and change condition of breaking the loop not reaching last row
        prev_len_cl = len(clusters[i])
        i += 1
    if cur_cl != 0 or i < (config_data.size[1] - 1):
        return False
    return True

config_data = get_data_from_yaml(CONFIGFILE)
if config_data.mode == "Photo" or config_data.mode == "Folder":
    if config_data.mode == "Photo":
        masks = [config_data.mask]
    if config_data.mode == "Folder":
        filenames = os.listdir(config_data.mask)
        masks = []
        for f in filenames:
            masks.append(config_data.mask + "/" + f)
    for mask_file in masks:
        mask = cv2.resize(cv2.imread(mask_file), config_data.size)
        h, _, _ = mask.shape
        if config_data.y_limits[1] < 1:
            mask = mask[int(h * config_data.y_limits[0]) : int(h * config_data.y_limits[1]), :, :]
        else:
            mask = mask[int(h * config_data.y_limits[0]) :, :, :]
        size = mask.shape
        
        
        t0 = time.time()
        if config_data.start[1] == 1.0:
            start_y = size[0] - 1
            start_x = int(size[1] * config_data.start[0])
        
        clusters = [] 
        for i in range (size[0]):
            clusters.append(None) 

        clusters[start_y] = [set([start_x])]
        row = start_y
        while row > 1 and clusters[row] != None:
            for j in range(len(clusters[row])):
                clusters[row][j] = update_wide(clusters[row][j], row, mask, size[1])
            clusters = update_up(clusters, row, mask)
            row -= 1
        
        end_y = row + 1
        row = end_y
        while row < start_y:
            clusters = update_down(clusters, row, start_y, mask)
            for j in range (len(clusters[row + 1])):
                clusters[row + 1][j] = update_wide(clusters[row + 1][j], row + 1, mask, size[1])
            row += 1
        clusters[start_y] = merge(clusters[start_y])
        print("Time of creating the graph, s", time.time() - t0)

        res = draw_clusters(mask, clusters, start_y, end_y)

        init_labels = get_data_from_txt(config_data.detections)
        init_labels = [i for i in init_labels if int(i[0]) == 5 or int(i[0]) == 6]#getting DL or DR tongues
        if len(init_labels) == 0:
            print('Keep moving. No tongues')
            cv2.putText(res, 'Keep moving! No tongues', (10, 20),fontFace=0, fontScale=1., color=(0,255,0))
        else:
            labels = copy.copy(init_labels)
            #drawing labels
            for i, label in enumerate(init_labels):
                labels[i] = pbx.convert_bbox(label[1:5], from_type='yolo', to_type='voc', image_size=config_data.size)
                res = cv2.rectangle(res, (labels[i][:2]), (labels[i][2:]), color=(128,128,128))
            cur_label, type_left, tongue_on_path = get_closest_tongue(labels, init_labels, clusters, mask)
            if not tongue_on_path:
                print('Keep moving. No tongues')
                cv2.putText(res, 'Keep moving! No tongues', (10, 20),fontFace=0, fontScale=1., color=(0,255,0))
            else:
                cur_cl = find_current_cluster(cur_label, clusters)
                left = define_main_path_left(cur_label, cur_cl, clusters, res)
                if not ( (left and type_left) or (not left and not type_left) ):
                    print('The position of the tongue is incorrect. Stoppage is essential!')
                    cv2.putText(res, 'Stoppage is essential!', (10, 20), fontFace = 0, fontScale=1., color=(255,0,0))
                else:
                    print('Keep moving.')
                    cv2.putText(res, 'Keep moving! Tongue is in a right position.', (10, 20),fontFace=0, fontScale=.5, color=(0,255,0))

        print("Total time, s", time.time() - t0)
        cv2.imshow("path", cv2.resize(res, [res.shape[1] // config_data.ratio, res.shape[0] // config_data.ratio]))
        cv2.imwrite(config_data.save_path, res)
        cv2.waitKey(0)
    cv2.destroyAllWindows()
    

