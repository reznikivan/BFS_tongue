import cv2
import numpy as np
import time
import os

import sys
sys.path.append('C:/Projects/Utils')
from config_util import get_data_from_yaml

CONFIGFILE = "C:/Projects/SLAM/Graph/config.yaml"
config_data = get_data_from_yaml(CONFIGFILE)

def is_path(elem):
    return not np.array_equal(elem, config_data.not_path_point)

def update_wide(cluster, row, mask, w):
    left_boundary, right_boundary = cluster

    # Update right boundary
    i = 1
    while right_boundary + i < w and is_path(mask[row, right_boundary + i]):
        i += 1
    right_boundary += i - 1

    # Update left boundary
    i = 1
    while left_boundary - i >= 0 and is_path(mask[row, left_boundary - i]):
        i += 1       
    left_boundary -= i - 1

    return [left_boundary, right_boundary]

def dist(cluster_1, cluster_2):
    if cluster_1[1] < cluster_2[0]:
        return cluster_2[0] - cluster_1[1]
    if cluster_2[1] < cluster_1[0]:
        return cluster_1[0] - cluster_2[1]
    return 0

def merge(clusters):
    merged = []
    clusters.sort(key=lambda x: x[0])  # Sort clusters based on their starting positions

    i = 0
    while i < len(clusters):
        curr_cluster = clusters[i]
        while i < len(clusters) - 1 and dist(curr_cluster, clusters[i + 1]) <= 1:
            curr_cluster = [min(curr_cluster[0], clusters[i + 1][0]), max(curr_cluster[1], clusters[i + 1][1])]
            i += 1
        merged.append(curr_cluster)
        i += 1

    return merged


def update_up(clusters, row, mask):
    up_clusters = []
    new_cluster = False
    for cluster in clusters[row]:
        p = cluster[0]
        if row >= 1:
            up_cluster = [p, p]
            while p <= cluster[1]:
                while p <= cluster[1] and not is_path(mask[row - 1, p]):
                    p += 1
                up_cluster[0] = p
                while p <= cluster[1] and is_path(mask[row - 1, p]):
                    new_cluster = True
                    p += 1
                up_cluster[1] = p - 1

                if new_cluster:
                    up_clusters.append(up_cluster)
                    up_cluster = [p, p]
                    new_cluster = False

    if len(up_clusters) > 0:
        clusters[row - 1] = merge(up_clusters)
    return clusters


def update_down(clusters, row, start_y, mask):
    down_clusters = []
    new_cluster = False
    for cluster in clusters[row]:
        p = cluster[0]
        if row < start_y:
            down_cluster = [p, p]
            while p <= cluster[1]:
                while p <= cluster[1] and not is_path(mask[row + 1, p]):
                    p += 1
                down_cluster[0] = p
                while p <= cluster[1] and is_path(mask[row + 1, p]):
                    new_cluster = True
                    p += 1
                down_cluster[1] = p - 1

                if new_cluster:
                    down_clusters.append(down_cluster)
                    down_cluster = [p, p]
                    new_cluster = False

        if len(down_clusters) > 0:
            clusters[row + 1] = merge(down_clusters)
    return clusters

def center(cluster):
    return (cluster[0] + cluster[1]) // 2

def draw_clusters(image, clusters, start_y, end_y):
    res = image
    for row in range (end_y, start_y + 1):
        for cluster in clusters[row]:
            center_p = center(cluster)
            res = cv2.circle(res, [center_p, row], config_data.radius, [255, 0, 0], config_data.thickness)
    return res



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

        clusters[start_y] = [[start_x, start_x]]
        row = start_y
        while row > 1:
            for j in range (len(clusters[row])):
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
        print("T, s", time.time() - t0)

        res = draw_clusters(mask, clusters, start_y, end_y)
        cv2.imshow("path", cv2.resize(res, [res.shape[1] // config_data.ratio, res.shape[0] // config_data.ratio]))
        cv2.waitKey(0)
    cv2.destroyAllWindows()
    

