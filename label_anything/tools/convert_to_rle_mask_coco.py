import json
import os
import sys
import cv2
import argparse
import numpy as np
from tqdm import tqdm
from itertools import groupby
from label_studio_converter.brush import decode_rle

import shutil

def parse_args():
    parser = argparse.ArgumentParser(description='Label studio convert to Coco fomat')
    parser.add_argument('--json_file_path',default='project.json', help='label studio output json')
    parser.add_argument('--out_dir',default='coco_format_files', help='output dir of Coco format json')
    parser.add_argument('--classes',default=None, help='Classes list of the dataset, if None please check the output.')

    args = parser.parse_args()
    return args


coco_format = {}
images = []
categories = []
annotations = []
bbox = []
area = []

def binary_mask_to_rle(binary_mask):
    rle = {'counts': [], 'size': list(binary_mask.shape)}
    counts = rle.get('counts')
    for i, (value, elements) in enumerate(groupby(binary_mask.ravel(order='F'))):
        if i == 0 and value == 1:
            counts.append(0)
        counts.append(len(list(elements)))
    return rle

def rle2mask(rle,height, width):
    """Convert RLE to mask

    :param rle: list of ints in RLE format
    :param height: height of binary mask
    :param width: width of binary mask
    :return: binary mask
    """
    mask = decode_rle(rle)
    mask = mask.reshape(-1,4)[:, 0]
    if mask.max()==255:
        mask=np.where(mask==255,1,0)

    # mask = mask[:len(mask)//4]

    return mask.reshape((height, width))

def format_to_coco(args):
    # 读取label studio格式的JSON文件
    json_file_path=args.json_file_path
    
    with open(json_file_path, 'r') as file:
        contents = json.loads(file.read())
    if sys.platform == 'linux':
        image_path_from=os.path.join('~/.local/share/label-studio/media/upload/',os.path.dirname(contents[0]['data']['image']).split('/')[-1])
    elif sys.platform == 'win32':
        image_path_from=os.path.join('~/AppData/Local/label-studio/label-studio/media/upload/',os.path.dirname(contents[0]['data']['image']).split('/')[-1])
    else:
        raise ValueError("The system does not support.")
    image_path_to=args.out_dir
    # 将coco格式保存到文件中
    output_dir=image_path_to
    output_ann_path=os.path.join(output_dir,'annotation')
    os.makedirs(output_ann_path, exist_ok=True)
    os.makedirs(os.path.join(image_path_to,'image'), exist_ok=True)
    # 初始化coco格式的字典
    coco_format = {
        "images": [],
        "categories": [],
        "annotations": []
    }

    #自定义类别标签顺序
    if args.classes is not None:
        for category in args.classes:
            coco_format["categories"].append({
            "id": len(coco_format["categories"]),
            "name": category
            })
    
    index_cnt=0
    # 遍历每个标注
    for index_annotation in tqdm(range(len(contents))):
        result = contents[index_annotation]['annotations'][0]['was_cancelled']

        if result == False:
            width_from_json = contents[index_annotation]["annotations"][0]["result"][0]["original_width"]
            height_from_json = contents[index_annotation]["annotations"][0]["result"][0]["original_height"]

            labels = contents[index_annotation]['annotations'][0]['result']

            for i in range(len(labels)):

                if 'rle' in labels[i]['value'].keys():
                    label_rel=labels[i]
                else:
                    continue

                image_id = contents[index_annotation]["id"]
                image_json_name_ = contents[index_annotation]["data"]['image'].split('/')[-1]
                image_json_name = image_json_name_.split('-', 1)[1]
                try:
                    category = label_rel['value']['brushlabels'][0]
                except:
                    category = label_rel['value']['rectanglelabels'][0]
                rle = label_rel['value']['rle']
                mask=rle2mask(rle,height_from_json,width_from_json)
                rle=binary_mask_to_rle(mask)
                contours, hierarchy = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                new_contours = []
                for contour in contours:
                    new_contours.extend(list(contour))
                new_contours = np.array(new_contours)
                x, y, w, h = cv2.boundingRect(new_contours)
                
                bbox = [x, y, w, h]
                area = w * h

                # 添加图像信息到coco格式
                coco_format["images"].append({
                    "id": image_id,
                    "file_name": image_json_name_,
                    "width": width_from_json,
                    "height": height_from_json
                })

                # 检查类别是否已经添加到categories变量中，如果没有，将其添加到categories变量
                if not any(d["name"] == category for d in coco_format["categories"]):
                    coco_format["categories"].append({
                        "id": len(coco_format["categories"]),
                        "name": category
                    })

                # 添加标注信息到coco格式
                coco_format["annotations"].append({
                    "id": index_cnt,
                    "image_id": image_id,
                    "category_id": [d["id"] for d in coco_format["categories"] if d["name"] == category][0],
                    "segmentation": rle,
                    "bbox": bbox,
                    "area": area,
                    'iscrowd': 0#rle format
                    
                })
                index_cnt+=1
            image_from=os.path.join(image_path_from,image_json_name_)
            image_to=os.path.join(image_path_to,'image',image_json_name)
            shutil.copy2(os.path.expanduser(image_from), image_to)

    classes_output=[d["name"] for d in coco_format["categories"]]
    print(classes_output)
    with open(os.path.join(output_ann_path,'output.json'), "w") as out_file:
        json.dump(coco_format, out_file, ensure_ascii=False, indent=4)

if __name__ == '__main__':
    args = parse_args()
    format_to_coco(args)
   
