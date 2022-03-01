#! /usr/bin/env python3

# srtgen.py
# Generate subtitles for video file
# https://github.com/milahu/srtgen
# MIT license

# config
config_language_code = 'en' # english https://cloud.google.com/speech-to-text/docs/languages
config_min_silence_len = 1500 # high value -> few long chunks
config_seek_step = 100 # high value -> split faster
config_silence_thresh = -14 # high value -> many short chunks

# api constants
api_filesize_limit = 10485760
api_duration_limit = 60 # API limit: 400 Inline audio exceeds duration limit. Please use a GCS URI.
api_audio_sample_rate = 16000

import sys
import io
import os
import codecs
import string
import subprocess
import hashlib
import math
import datetime

# speech recognition
from google.cloud import speech_v1 as speech
import google.cloud.speech_v1 as enums
from google.cloud.speech_v1 import types

# audio processing
import pydub # pydub.AudioSegment
import pydub.silence # pydub.silence.split_on_silence

# logging messages go to stderr
def log(*args, **kwargs):
    args = ["log: " + " ".join([str(a) for a in args]).replace("\n", "\nlog: ")]
    #args = ["log:"] + list(args)
    stderr(*args, **kwargs)

def stderr(*args, **kwargs):
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)

enable_debug = False

# debug messages go to stderr
def dbg(*args, **kwargs):
    if not enable_debug:
        return
    args = ["dbg:"] + list(args)
    stderr(*args, **kwargs)

output_file_path = None
output_file_handle = None

# output goes to stdout and file
def out(*args, **kwargs):
    print(*args, **kwargs)
    if output_file_handle:
        log(f"writing to {output_file_path}")
        kwargs["file"] = output_file_handle
        print(*args, **kwargs)
        output_file_handle.flush()
    else:
        log("not writing to output_file_path") # this should not happen

def log_usage():
    argv0 = os.path.basename(sys.argv[0])
    stderr(f"usage")
    stderr(f"  {argv0} --apikey path/to/apikey.json path/to/input-video.mp4")
    stderr()
    stderr(f"config files")
    stderr(f"  $HOME/.config/srtgen/apikey.json")
    stderr()
    stderr(f"environment variables")
    stderr(f"  GOOGLE_APPLICATION_CREDENTIALS=path/to/apikey.json {argv0} path/to/input-video.mp4")
    stderr()
    stderr(f"keyfile")
    stderr(f"  This program requires a Google account and an API key")
    stderr(f"  https://console.cloud.google.com/projectcreate")

def check_api_key():
    global apikey_from_argv
    apikey_candidates = [
        apikey_from_argv,
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        os.environ.get("HOME") + "/.config/srtgen/apikey.json",
    ]
    for apikey in apikey_candidates:
        if not apikey:
            continue
        log("trying api key", apikey)
        if os.path.exists(apikey):
            log("using api key", apikey)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = apikey
            return
    log("apikey is missing")
    log_usage()
    sys.exit(1)

def format_time_srt(seconds):
    return datetime.datetime.fromtimestamp(seconds, tz=datetime.timezone.utc).strftime('%H:%M:%S,%f')[:-3] # note: comma for SRT format

def transcribe_file(input_video_path):
    """Transcribe the given video file."""

    global output_file_path
    global output_file_handle

    input_video_hash = hashlib.sha1(open(input_video_path, "rb").read())
    input_video_hash = input_video_hash.hexdigest()
    log(f"input_video_hash = {input_video_hash}")

    tempdir = f"{input_video_hash}-{os.path.basename(input_video_path)}"[0:240] # limit 255 chars
    tempdir = os.path.join("output", tempdir)
    log(f"tempdir = {tempdir}")
    os.makedirs(tempdir, exist_ok=True)

    output_file_path = os.path.join(tempdir, "output_file.srt")
    output_file_handle = open(output_file_path, "w")
    log(f"output_file_path = {output_file_path}")

    speech_file = os.path.join(tempdir, "speech_file.flac")
    log(f"speech_file = {speech_file}")

    if os.path.exists(speech_file):
        log("speech_file exists -> dont run ffmpeg")
    else:
        ffmpeg_args = ["ffmpeg", "-loglevel", "warning", "-stats", "-i", input_video_path, "-f", "flac", "-ar", str(api_audio_sample_rate), "-ac", "1", "-vn", speech_file]
        log(f"ffmpeg_args = {ffmpeg_args}")
        subprocess.run(ffmpeg_args)

    audio = pydub.AudioSegment.from_file(speech_file)
    chunk_list = [audio]

    size = os.stat(speech_file).st_size
    if size > api_filesize_limit or audio.duration_seconds > api_duration_limit:
        do_split_on_silence = True # benefit: more precision in timestamps?
        if do_split_on_silence:
            log(f"audio file is too big -> splitting audio on silence")
            # https://www.geeksforgeeks.org/python-speech-recognition-on-large-audio-files/
            log(f"  actual: {size:10d} bytes")
            log(f"  limit:  {api_filesize_limit:10d} bytes")

            log(f"splitting audio on silence")
            #chunk_list = split_on_silence( # patched version
            chunk_list = pydub.silence.split_on_silence(
                audio,
                min_silence_len = config_min_silence_len, # high value -> few long chunks
                silence_thresh = audio.dBFS + config_silence_thresh,
                keep_silence = True, # preserve absolute time
                #keep_silence = "after", # preserve absolute time. requires the patched version of split_on_silence
                seek_step = config_seek_step,
            )
            log(f"found {len(chunk_list)} chunks")

            chunk_list_new = []
            for chunkid, c in enumerate(chunk_list):
                if c.duration_seconds > api_duration_limit:
                    dbg(f"chunk {chunkid} is too long: {c.duration_seconds} seconds")
                    for i in range(0, math.ceil(c.duration_seconds / api_duration_limit)):
                        # frame_rate: frames per second
                        # TODO round?
                        f1 = c.frame_rate * api_duration_limit * i
                        f2 = c.frame_rate * api_duration_limit * (i + 1)
                        dbg("split chunk by frame:", f1, f2)
                        chunk_list_new.append(c.get_sample_slice(f1, f2))
                else:
                    chunk_list_new.append(c)
            chunk_list = chunk_list_new
            log(f"split by length to {len(chunk_list)} chunks")
        else:
            # split only by time
            log("audio.duration_seconds =", audio.duration_seconds)
            chunk_list = []
            for i in range(0, math.ceil(audio.duration_seconds / api_duration_limit)):
                # frame_rate: frames per second
                f1 = audio.frame_rate * api_duration_limit * i
                f2 = audio.frame_rate * api_duration_limit * (i + 1)
                log("split chunk by frame:", f1, f2)
                chunk_list.append(audio.get_sample_slice(f1, f2))

    client = speech.SpeechClient()
    response = None

    total_time = 0.0

    subtitle_index = 1 # TODO remove
    sub_index = 1

    for chunk_id, audio_chunk in enumerate(chunk_list):

        chunk_file = os.path.join(tempdir, f"chunk{chunk_id:04d}.flac")
        log(f"chunk_file = {chunk_file}")

        #log(f"{chunk_file}: total_time = {total_time}")
        #log(f"{chunk_file}: duration = {audio_chunk.duration_seconds} seconds")
        # specify the bitrate to be 192 k
        audio_chunk.export(chunk_file, format = "flac") # default format = mp3

        with io.open(chunk_file, 'rb') as audio_file:
            content = audio_file.read()

        audio = types.RecognitionAudio(content=content)

        #config_language_phrases = [] # unusual words, technical terms, acronyms

        config = types.RecognitionConfig(
            encoding=enums.RecognitionConfig.AudioEncoding.FLAC,
            #sample_rate_hertz=16000, # TODO verify
            language_code=config_language_code,
            enable_word_time_offsets=True, # https://cloud.google.com/speech-to-text/docs/async-time-offsets
            #phrases=config_language_phrases, # FIXME unknown key
        )

        operation = client.long_running_recognize(
            config=config,
            audio=audio,
        )

        try:
            this_response = operation.result(timeout=90)
        except Exception as e:
            log(f"{chunk_file}: duration = {audio_chunk.duration_seconds} seconds")
            log(f"{chunk_file}: total_time = {total_time}")
            log(e)
            raise

        if len(this_response.results) == 0:
            total_time += audio_chunk.duration_seconds
            continue

        seconds_per_subtitle = 3 # TODO ...

        def round_2f(f):
            """round to 1 digit precision, for example 0.099 -> 0.1"""
            #return round(f * 100) / 100
            return round(f, 1)
            return round(f, 2)
            
        for result in this_response.results:
            alternative = result.alternatives[0]
            #log("Transcript: {}".format(alternative.transcript))
            #log("Confidence: {}".format(alternative.confidence))

            # magic numbers. empirical values.
            # may need fine-tuning for different input data
            average_voice_speed = 12
            min_voice_speed = 10

            sub_words = []
            sub_start = None

            last_end_time = None

            for word_info in alternative.words:
                word = word_info.word
                start_time = round_2f(total_time + word_info.start_time.total_seconds())
                end_time = round_2f(total_time + word_info.end_time.total_seconds())

                #log(f"Word: {word}, start_time: {start_time.total_seconds()}, end_time: {end_time.total_seconds()}")
                #log(f"Word: {start_time.total_seconds()} - {end_time.total_seconds()}: {word}")

                if last_end_time and last_end_time < start_time:
                    log("\n  ---- word pause detected from start_time\n") # pause before this word
                    # TODO verify
                    if len(sub_words) > 0:
                        sub_end = last_end_time
                        out(f"{sub_index}\n{format_time_srt(sub_start)} --> {format_time_srt(sub_end)}\n{' '.join(sub_words)}\n")
                        sub_index += 1
                        sub_words = []
                        sub_start = None

                diff_time = round_2f(end_time - start_time)
                voice_speed = round(len(word) / diff_time, 4) if diff_time > 0 else 99 # how many characters per second

                if voice_speed < min_voice_speed:
                    # this means a short word has a long diff_time
                    # this means there was silence before the word
                    # and start_time is NOT the start of the word.
                    # end_time is more reliable,
                    # so we take an average voice_speed of 12
                    # and estimate the real start_time

                    if len(sub_words) > 0:
                        sub_end = last_end_time
                        out(f"{sub_index}\n{format_time_srt(sub_start)} --> {format_time_srt(sub_end)}\n{' '.join(sub_words)}\n")
                        sub_index += 1
                        sub_words = []
                        sub_start = None
 
                    voice_speed_2 = average_voice_speed
                    end_time_2 = end_time
                    diff_time_2 = round_2f(len(word) / voice_speed_2)
                    start_time_2 = round_2f(end_time_2 - diff_time_2)
                    #voice_speed = average_voice_speed
                    #log(f"\n  ---- word pause detected from voice_speed {voice_speed} = {len(word):2d} / {diff_time}\n") # pause before this word

                    if sub_start == None:
                        sub_start = start_time_2

                    log(f"\n  ---- word pause detected from voice_speed\n") # pause before this word
                    log(f"- {start_time} --> {end_time}: {len(word):2d} / {diff_time} = {voice_speed:5.2f}")
                    log(f"+ {start_time_2} --> {end_time_2}: {len(word):2d} / {diff_time_2} = {voice_speed_2:5.2f}: {word}")
                    #log(f"  {start_time_2} --> {end_time_2}: {len(word):2d} / {diff_time_2} = {voice_speed_2:5.2f}: {word}")

                else:
                    if sub_start == None:
                        sub_start = start_time
                    log(f"  {start_time} --> {end_time}: {len(word):2d} / {diff_time} = {voice_speed:5.2f}: {word}")

                sub_words.append(word)
                last_end_time = end_time

            if len(sub_words) > 0:
                sub_end = last_end_time
                out(f"{sub_index}\n{format_time_srt(sub_start)} --> {format_time_srt(sub_end)}\n{' '.join(sub_words)}\n")
                sub_index += 1

        if response == None:
            response = this_response
        else:
            response.results += this_response.results

        total_time += audio_chunk.duration_seconds
        subtitle_index += 1

    log(f"recognized all {len(chunk_list)} chunks")
    return response

apikey_from_argv = None

def main():
    global apikey_from_argv
    # parse arguments
    # TODO better ... use argparse
    try:
        if sys.argv[1] == "--apikey":
            log(f"using api key from argument: --apikey {sys.argv[2]}")
            apikey_from_argv = sys.argv[2]
            sys.argv = sys.argv[0:1] + sys.argv[3:]

        input_video_path = sys.argv[1]
    except Exception as e:
        log_usage()
        if isinstance(e, IndexError):
            sys.exit(1)
        raise

    check_api_key()

    output_path = './output/'
    if not os.path.exists(output_path):
        os.mkdir(output_path)

    try:
        if input_video_path.startswith('gs://'):
            raise Exception("not implemented: gs protocol")
            #transcribe_gcs(input_video_path)
        else:
            transcribe_file(input_video_path)
        log("Transcribe done")
    except BaseException as e:
        log('error: transcribe failed!', e)
        raise


if __name__ == "__main__":
    main()
