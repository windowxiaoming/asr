#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  3 15:06:43 2018

@author: dalonlobo
"""
from __future__ import absolute_import, division, \
                        print_function, unicode_literals

import os
import sys
import argparse
import logging
import logging.handlers
import glob
import pandas as pd

from timeit import default_timer as timer
from utils import run_command, convert_mp4_to_audio, \
                    train_validate_test_split, clean_srt_min_duration
from download_from_youtube import download_all_videos
from split_video_on_srt_time import split_video_on_srt_time

if __name__ == "__main__":
    """
    This script will download Sadguru videos, and preprocess them,
    3 folders will be created, train, dev and test, which will have the csv and 
    wav chunks
    """
    logs_path = os.path.basename(__file__) + ".logs"
    logger = logging.getLogger("__main__")
    logger.setLevel(logging.DEBUG)
    rotatinghandler = logging.handlers.RotatingFileHandler(logs_path, maxBytes=500000, backupCount=100)
    rotatinghandler.setLevel(logging.DEBUG)
    # Send mail when exception occurs
    smtp_handler = logging.handlers.SMTPHandler(
                            mailhost=("smtp.gmail.com", 587),
                            fromaddr="noreply_dalonlobo@gmail.com",
                            toaddrs="dalonlobo@gmail.com",
                            subject="Message from import_sadguru.py",
                            credentials=('dalonlobo@gmail.com', 'imozeuhciixcnznq'),
                            secure=())
    smtp_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter(
                    '%(asctime)s [%(name)s:%(levelname)s] [%(filename)s:%(funcName)s] #%(lineno)d: %(message)s')
    smtp_handler.setFormatter(formatter)
    rotatinghandler.setFormatter(formatter)
    logger.addHandler(rotatinghandler)
    logger.addHandler(smtp_handler)
    print("Logs are in ", os.path.abspath(logs_path), file=sys.stderr)
    print("Run the following command to view logs:", file=sys.stderr)
    print("tail -f {}".format(os.path.abspath(logs_path)), file=sys.stderr)
    try:
        logger.info("#########################")
        logger.info("....Starting program.....")
        logger.info("#########################")
        process_start_time = timer()
        parser = argparse.ArgumentParser(description="""
                                         This script will import sadguru videos and preprocess them, 
                                         so that you can train deepspeech model""")
        parser.add_argument('--vidlist', '-v', type=str,  
                            help='Path to the excel file containing list of videos to download')
        parser.add_argument('--destpath', '-d', type=str, default='tmp',  
                            help='Path to store the video files')
        parser.add_argument('--checkpoint_dir', '-c', type=str, default='checkpoint', 
                            help='Path to checkpoint directory')
        parser.add_argument('--stop', '-n', type=str, default='n', 
                            help="Don't stop if video directory exists (y or n)")
#        args = parser.parse_args(["--vidlist", "SADHGuru Channel Videos tmp.xlsx",
#                                  "--checkpoint_dir", "tmp/checkpoint",
#                                  "--destpath", "tmp"])
        args = parser.parse_args()
        # Path to the checkpoint directory
        checkpoint_dir = args.checkpoint_dir
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)
        checkpoint_dir = os.path.abspath(checkpoint_dir)
        # Path to the destination folder, where videos will be saved 
        destpath = os.path.abspath(args.destpath)
        # path to excel  file containing the list of videos to download
        vidlist = os.path.abspath(args.vidlist)   
        # Videos will be stored here
        videospath = os.path.join(os.path.abspath(args.destpath), "Videos")
        # Create the destination folder if it does not exist
        if not os.path.exists(videospath):
            logger.info("Creating the directory: " + videospath)
            os.makedirs(videospath)
        else:
            print("Videos directory already exists", file=sys.stderr)
            try:
               input = raw_input # Py 2 and 3 compatibility
            except NameError:
               pass
            if args.stop == "y":
                user_input = input("Do you want to continue? y or n\n")
                if user_input != "y":
                    sys.exit(0)
                
        # Read the videos list from excel file
        # Columns are VideoID,	Link, 	Transcribed
        df_to_download = pd.read_excel(vidlist)    
        # Retain only the videos which have transcription
        df_to_download = df_to_download[df_to_download.Transcribed == 1]
        logger.debug("List of videos that will be downloaded: ")
        logger.debug(df_to_download.Link)
        logger.info("Saving the videos to: " + videospath)
        # Download all the videos in the list to the destination folder
        flag = download_all_videos(videospath, df_to_download)
        if not flag:
            logger.error("Download the videos again, something went wrong!")
            print("Download the videos again, something went wrong!", file=sys.stderr)
            sys.exit(-1)
        # Clean the srt for subtitles under 1s
        for dirs in os.listdir(videospath):
            directory = os.path.join(videospath, dirs)
            if not os.path.isdir(directory):
                continue # If its not directory, just continue
            logger.info("Clean the srt for subtitles under 1s in following directory:")
            logger.info(directory)
            try:
                clean_srt_min_duration(glob.glob(directory + "/*.srt")[0], DURATION=1000)
            except IndexError:
                logger.error("No srt file in: " + directory)
        logger.info("Cleaning of srt for subs below 1s duration done")
        # Splitting the videos 
        for dirs in os.listdir(videospath):
            directory = os.path.join(videospath, dirs)
            if not os.path.isdir(directory):
                continue # If its not directory, just continue
            logger.info("Splitting the video in following directory:")
            logger.info(directory)
            split_video_on_srt_time(videospath, checkpoint_dir, directory, dirs)
        print("All the videos are converted to audio and split successfully", file=sys.stderr)
        # Merge the csv files and randomly split them into train, dev, text in the ratio
        # 70:20:10
        logger.info("Merging the csv files")  
        # Path to csv files
        csv_files_path = os.path.join(destpath, "Videos")
        csv_files_list = glob.glob(csv_files_path + "/*.csv")
        logger.info("List of csv files")
        logger.info(csv_files_list)
        # Read the first dataframe
        df = pd.read_csv(csv_files_list[0])
        # Append to the main dataframe
        for csv_file in csv_files_list[1:]:
            temp_df = pd.read_csv(csv_file)
            df = df.append(temp_df)
        logger.info("All the csv files are merged, shape of the total dataframe is: ")
        logger.info(df.shape)
        # Drop the null values
        df.dropna(inplace=True)
        train_df, dev_df, test_df = train_validate_test_split(df, train_percent=.7, 
                                                              validate_percent=.2, seed=200)
        print("All the dataframes are split into train, dev and test", file=sys.stderr)
        logger.info("All the dataframes are split into train, dev and test")
        logger.info("Shape of train, dev, test are below: ")
        logger.info(train_df.shape)
        logger.info(dev_df.shape)
        logger.info(test_df.shape)
        logger.info("Saving the files to: " + destpath)
        train_df.to_csv(os.path.join(destpath, "sadguru-other-train.csv"), index=False)
        dev_df.to_csv(os.path.join(destpath, "sadguru-other-dev.csv"), index=False)
        test_df.to_csv(os.path.join(destpath, "sadguru-other-test.csv"), index=False)
        logger.info('Entire program ran in {} minutes'.format((timer() - process_start_time) / 60))
    except SystemExit as e:
        print("System exit command issued with code: " + str(e), file=sys.stderr)
        logger.error("System exit command issued with code: " + str(e))
    except Exception as e:
        logging.exception(e)
    finally:
        logger.info("#########################")
        logger.info(".....Exiting program.....")
        logger.info("#########################")
        # Following exception is just to inform me that the program has ended
        logger.exception("Program has completed successfully")
        print("#### Exiting Program ####", file=sys.stderr)
    
    
    
    
    
    
    
    
    
    
