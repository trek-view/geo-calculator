# -*- coding: utf-8 -*-
# -------------------------------------------------------------------------------
# Author: automate.IT
# Contact: info@automate.IT
# Created: 2020-06-05
# Copyright: automate.IT
# Licence: GNU AGPLv3
# -------------------------------------------------------------------------------

import math
import argparse
import sys
import ntpath
import time
import os
from pathlib import Path

import pandas as pd
import exiftool

def calculate_initial_compass_bearing(pointA, pointB):
    '''
    Calculate the compass bearing (azimuth) between two points 
    on the earth (specified in decimal degrees)
    https://github.com/trek-view/tourer/blob/latest/utils.py#L114
    '''
    if (type(pointA) != tuple) or (type(pointB) != tuple):
        raise TypeError('Only tuples are supported as arguments')

    lat1 = math.radians(pointA[0])
    lat2 = math.radians(pointB[0])

    diffLong = math.radians(pointB[1] - pointA[1])

    x = math.sin(diffLong) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - (math.sin(lat1)
            * math.cos(lat2) * math.cos(diffLong))

    initial_bearing = math.atan2(x, y)
    initial_bearing = math.degrees(initial_bearing)
    compass_bearing = (initial_bearing + 360) % 360

    return compass_bearing


def haversine(lon1, lat1, lon2, lat2):
    '''
    Calculate the great circle distance between two points 
    on the earth (specified in decimal degrees)
    https://github.com/trek-view/tourer/blob/latest/utils.py#L134
    '''
    lon1, lat1, lon2, lat2 = map(math.radians, [lon1, lat1, lon2, lat2])
    dlon = lon2 - lon1 
    dlat = lat2 - lat1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371

    distance = (c * r) * 1000

    return distance


def get_files(path, listdir):
    '''
    Return a list of files, or directories.
    '''
    list_of_files = []

    for item in os.listdir(path):
        itemPath = os.path.abspath(os.path.join(path,item))
        
        if listdir:
            if os.path.isdir(itemPath):
                list_of_files.append(itemPath)
        else:
            if os.path.isfile(itemPath):
                list_of_files.append(itemPath)

    return list_of_files


def filter_metadata(dict_metadata, key, discard):
    '''
    For a given set of metadata for an image, return every key-value
    taking into account whether to discard it or not.
    '''
    if discard == True:
        try:
            return dict_metadata[key]
        except KeyError:
            #discard is True -> Set the value of the key to NaN, this picture will be thrown away
            return float('NaN')
    else:
        #discard is False -> throw a Keyerror and stop the program when certain metadata is not available
        return dict_metadata[key]

    
def parse_metadata(dict_metadata, keys, discard):
    '''
    Main function using filter_metadata() to process each key in a metadata object
    '''
    values = []
    for key in keys:
        values.append(filter_metadata(dict_metadata, key, discard))
    return values

def clean_up_new_files(OUTPUT_PHOTO_DIRECTORY, list_of_files):
    '''
    As Exiftool creates a copy of the original image when processing,
    the new files are copied to the output directory,
    original files are renamed to original filename.
    '''
    print('Cleaning up old and new files...')
    if not os.path.isdir(os.path.abspath(OUTPUT_PHOTO_DIRECTORY)):
        os.mkdir(os.path.abspath(OUTPUT_PHOTO_DIRECTORY))

    for image in list_of_files:
        image_head, image_name = ntpath.split(image)
        try:
            os.rename(image, os.path.join(os.path.abspath(OUTPUT_PHOTO_DIRECTORY), image_name))
            os.rename(os.path.join(os.path.abspath(image_head), '{0}_original'.format(image_name)), image)
        except PermissionError:
            print('Image {0} to move is still in use by Exiftools process. Waiting...'.format(image_name))
            time.sleep(3)
            os.rename(image, os.path.join(os.path.abspath(OUTPUT_PHOTO_DIRECTORY), image_name))
            os.rename(os.path.join(os.path.abspath(image_head), '{0}_original'.format(image_name)), image)

def add_azimuth_pitch(args):
    '''
    Main function.
    A function that uses Exiftool add a calculated azimuth and pitch in relation to its next sequential images
    '''
    #Process import parameters
    CONNECTION_TYPE        = 'GPS_DATETIME' if args.connection_type in ['time', 'Time', 't', 'T'] else 'IMAGE_NAME' # 'GPS_DATETIME' for sorting on 'time' or 'IMAGE_NAME' for sorting on 'filename'
    CONNECTION_ORDER       = True  if args.connection_order in ['ascending', 'Ascending', 'a', 'A'] else False # True for sorting 'ascending' or False for sorting'decending'
    DISCARD                = True if args.discard == True else False

    PATH                   = Path(__file__)
    INPUT_PHOTO_DIRECTORY  = args.input_directory
    OUTPUT_PHOTO_DIRECTORY = args.output_directory

    #Often the exiftool.exe will not be in Windows's PATH
    if args.executable_path == 'No path specified':
        if 'win' in sys.platform and not 'darwin' in sys.platform:
            if os.path.isfile(os.path.join(PATH.parent.resolve(), 'exiftool.exe')):
                exiftool.executable = os.path.join(PATH.parent.resolve(), 'exiftool.exe')
            else:
                input("""Executing this script on Windows requires either the "-e" option
                    or store the exiftool.exe file in the working directory.\n\nPress any key to quit...""")
                quit()
        else:
            pass #exiftool.executable  = 'exiftool', which if in OS PATH will be OK for mac and linux

    else:
        exiftool.executable = args.executable_path

    #Get files in directory
    list_of_files = get_files(INPUT_PHOTO_DIRECTORY, False)

    #Get metadata of each file in list_of_images
    with exiftool.ExifTool() as et:
        list_of_metadata = [{'IMAGE_NAME':image, 'METADATA':et.get_metadata(image)} for image in list_of_files]

    #Create dataframe from list_of_metadata with image name in column and metadata in other column 
    df_images = pd.DataFrame(list_of_metadata)

    keys = ['Composite:GPSDateTime', 'Composite:GPSLatitude', 'Composite:GPSLongitude', 'Composite:GPSAltitude']
    df_images[['GPS_DATETIME', 'LATITUDE', 'LONGITUDE', 'ALTITUDE']] = df_images.apply(lambda x: parse_metadata(x['METADATA'], keys, DISCARD), axis=1, result_type='expand')

    #remove discarded images.
    df_images.dropna(axis=0, how='any', inplace=True)

    #Sort images
    df_images.sort_values(CONNECTION_TYPE, axis=0, ascending=CONNECTION_ORDER, inplace=True)

    #Create new column with next value
    df_images['GPS_DATETIME_NEXT'] = df_images['GPS_DATETIME'].shift(-1)
    df_images['LATITUDE_NEXT']     = df_images['LATITUDE'].shift(-1)
    df_images['LONGITUDE_NEXT']    = df_images['LONGITUDE'].shift(-1)
    df_images['ALTITUDE_NEXT']     = df_images['ALTITUDE'].shift(-1)

    #Calculate the Azimuth, Distance and resulting Pitch
    df_images['AZIMUTH']  = df_images.apply(lambda x: calculate_initial_compass_bearing((x['LATITUDE'], x['LONGITUDE']), (x['LATITUDE_NEXT'], x['LONGITUDE_NEXT'])),axis=1)
    df_images['DISTANCE'] = df_images.apply(lambda x: haversine(x['LONGITUDE'], x['LATITUDE'], x['LONGITUDE_NEXT'], x['LATITUDE_NEXT']),axis=1)
    df_images['PITCH']    = (df_images['ALTITUDE_NEXT'] - df_images['ALTITUDE']) / df_images['DISTANCE']

    #Last picture gets value from previous picture for Azimuth, Distance & Pitch
    df_images.iat[-1, df_images.columns.get_loc('AZIMUTH')]  = df_images['AZIMUTH'].iloc[-2]
    df_images.iat[-1, df_images.columns.get_loc('DISTANCE')] = df_images['DISTANCE'].iloc[-2]
    df_images.iat[-1, df_images.columns.get_loc('PITCH')]    = df_images['PITCH'].iloc[-2]

    #Edit the metadata of the images
    with exiftool.ExifTool() as et:
        for index, row in df_images.iterrows():
            et.execute(bytes('-GPSPitch={0}'.format(row['PITCH']), 'utf-8'), bytes("{0}".format(row['IMAGE_NAME']), 'utf-8'))
            et.execute(bytes('-PoseHeadingDegrees={0}'.format(row['AZIMUTH']), 'utf-8'), bytes("{0}".format(row['IMAGE_NAME']), 'utf-8'))
            et.execute(bytes('-GPSImgDirection={0}'.format(row['AZIMUTH']), 'utf-8'), bytes("{0}".format(row['IMAGE_NAME']), 'utf-8'))
            et.execute(bytes('-CameraElevationAngle={0}'.format(row['PITCH']), 'utf-8'), bytes("{0}".format(row['IMAGE_NAME']), 'utf-8'))
            et.execute(bytes('-PosePitchDegrees={0}'.format(row['PITCH']), 'utf-8'), bytes("{0}".format(row['IMAGE_NAME']), 'utf-8'))

    clean_up_new_files(OUTPUT_PHOTO_DIRECTORY, list_of_files)

    input('\nMetadata successfully added to images.\n\nCreated by automate.IT and Trekview.org, for your convenience!\n\nPress any key to quit')
    quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'Azimuth Pitch metadata setter')

    parser.add_argument('-c', '--connection-type', 
                        action='store', 
                        dest='connection_type',
                        help='Connection Type: "time" (capture time of image) or "filename".')

    parser.add_argument('-o', '--connection-order', 
                        action='store', 
                        default='ascending',
                        dest='connection_order',
                        help='Connection Order: "ascending" or "descending".')

    parser.add_argument('-d', '--discard', 
                        action='store_true', 
                        default=False,
                        dest='discard',
                        help='Force the program to continue if images do not have all required metadata. Such images will be discarded.')

    parser.add_argument('-e', '--exiftool-exec-path', 
                        action='store', 
                        default='No path specified',
                        dest='executable_path',
                        help='Optional: path to Exiftool executionable.')

    parser.add_argument('input_directory', 
                        action="store", 
                        help='Path to input folder.')
    parser.add_argument('output_directory', 
                        action="store", 
                        help ='Path to output folder.')

    parser.add_argument('--version', 
                        action='version', 
                        version='%(prog)s 1.0')

    args = parser.parse_args()

    add_azimuth_pitch(args)
