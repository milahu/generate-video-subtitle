#! /usr/bin/env -S python3 -u

# https://cloud.google.com/speech-to-text/docs/basics

"""
Note: In this file, the default config:
        1. sample_rate_hertz=16000,
        2. language_code='zh'
        3. encoding='FLAC'
        4. this config would set several phrases
            for specific vedio "Savvy _June Cut_final.mp4"
"""

# config
config_language_code = 'en' # english
config_language_phrases = [] # unusual words, technical terms, acronyms
config_min_silence_len = 1500 # high value -> few long chunks
config_seek_step = 100 # high value -> split faster
config_silence_thresh = -14 # high value -> many short chunks

api_filesize_limit = 10485760
api_duration_limit = 60 # API limit: 400 Inline audio exceeds duration limit. Please use a GCS URI.


import sys
import io
import os
import codecs
import timestr
import string
import subprocess
import hashlib

from google.cloud import speech_v1 as speech
import google.cloud.speech_v1 as enums
from google.cloud.speech_v1 import types

import pydub # pydub.AudioSegment
import pydub.silence # pydub.silence.split_on_silence
#from pydub_silence import split_on_silence # patched version

import math # todo move
from datetime import datetime, timezone


# logging messages go to stderr
def log(*args, **kwargs):
    args = ["log: " + " ".join(args).replace("\n", "\nlog: ")]
    #args = ["log:"] + list(args)
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)

enable_debug = False

# debug messages go to stderr
def dbg(*args, **kwargs):
    if not enable_debug:
        return
    args = ["dbg:"] + list(args)
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)

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
    log()
    log(f"usage:")
    log(f"  {sys.argv[0]} --apikey path/to/keyfile.json input-video.mp4")
    log(f"  GOOGLE_APPLICATION_CREDENTIALS=path/to/keyfile.json {sys.argv[0]} input-video.mp4")
    log()

def check_api_key():
    p = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not p or not os.path.exists(p):
        log("please set --apikey or GOOGLE_APPLICATION_CREDENTIALS")
        log_usage()
        sys.exit(1)
    else:
        log("using api key", os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"))

flac_audio_rate = 16000

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
        ffmpeg_args = ["ffmpeg", "-loglevel", "warning", "-stats", "-i", input_video_path, "-f", "flac", "-ar", str(flac_audio_rate), "-ac", "1", "-vn", speech_file]
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

    if False:
        # collect chunks into groups
        # https://stackoverflow.com/a/312464/10440128
        def chunks(L, n):
            """Yield successive n-sized chunks from list L."""
            for i in range(0, len(L), n):
                yield L[i:i+n]

        chunks_per_group = 1

        # FIXME Inline audio exceeds duration limit. [audio is too long]
        log(f"grouping chunks into {math.ceil(len(chunk_list) / chunks_per_group)} chunks")
        chunk_list_new = []
        for chunk_id, chunk_group in enumerate(chunks(chunk_list, chunks_per_group)):
            audio_chunk = chunk_group[0]
            for c in chunk_group[1:]:
                audio_chunk += c
            chunk_list_new.append(audio_chunk)
        chunk_list = chunk_list_new

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

        def format_time_srt(seconds):
            return datetime.fromtimestamp(seconds, tz=timezone.utc).strftime('%H:%M:%S,%f')[:-3] # note: comma for SRT format

        # old code ...
        if False:
            # FIXME t1s is wrong
            t1s = format_time_srt(total_time)
            t2s = format_time_srt(total_time + seconds_per_subtitle)

            sentences = [result.alternatives[0].transcript.strip() for result in this_response.results]

            out(f"{subtitle_index}\n{t1s} --> {t2s}\n" + " ".join(sentences) + "\n")

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


# TODO refactor or remove
def transcribe_gcs(gcs_uri):
    """Transcribe the given audio file asynchronously."""
    client = speech.SpeechClient()

    audio = types.RecognitionAudio(uri=gcs_uri)
    config = types.RecognitionConfig(
        encoding=enums.RecognitionConfig.AudioEncoding.FLAC,
        sample_rate_hertz=16000,
        language_code='zh',
        speech_contexts=[
            speech.types.SpeechContext(
                #phrases=[
                #    '思睿', '在思睿', '海外教育', '双师', '贴心的辅导', '授课', '云台录播', '讲义', '赢取',
                #    '引起', '只为', '相结合', '坚持而努力', '越来越近', '思睿用爱'
                #]
            )
        ],
        enable_word_time_offsets=True,
        enable_automatic_punctuation=True)
    # [START speech_python_migration_async_response]
    operation = client.long_running_recognize(config=config, audio=audio)
    # [END speech_python_migration_async_request]

    log('Waiting for operation to complete...')
    response = operation.result(timeout=90)
    return response


def write_into_doc(response, output_path):
    #  from google.protobuf.json_format import MessageToJson
    #  with open('./test-json.txt', 'w', encoding='utf-8') as writer:
    #      json.dump(MessageToJson(source), writer, ensure_ascii=False)

    log('Waiting for writing doc to complete...')

    with codecs.open(output_path + 'transcript-text.txt', 'w',
                     'utf-8') as writer:
        for result in response.results:
            alternative = result.alternatives[0].transcript
            writer.write(alternative)


def write_into_subtitle(response, output_path):

    log('Waiting for writing subtitle to complete...')

    # read the chinese punctuation
    with codecs.open(output_path + 'transcript-text.txt', 'r',
                     'utf-8') as reader:
        words = reader.read()
        punctuation = dict()
        punc_index_list = []
        punc_index = 0
        for w in words:
            if not w.isalpha() and w not in string.whitespace:
                punctuation[str(punc_index)] = w
                punc_index_list.append(punc_index)
                punc_index += 1
            elif w.isalpha():
                punc_index += 1

    with codecs.open(output_path + 'subtitle-with-punctuation.srt', 'w',
                     'utf-8') as writer:
        i = 1  # setting the sequence number for srt
        init = True  # init flag
        word_index = 0
        curr = 0  # current punctuation number
        for result in response.results:
            alternative = result.alternatives[0]
            line = ""  # each line contain 10 words
            counter = 0  # word counter in a line
            # how many words remaining in this result
            num_woeds = len(alternative.words)
            start_next_para = True
            # loop the word in the result
            for word_info in alternative.words:
                word_index += 1
                num_woeds -= 1
                counter += 1
                word = word_info.word
                if init:
                    start_time = word_info.start_time
                    str_start = timestr.timefm(start_time.seconds +
                                               start_time.nanos * 1e-9)
                    init = False
                if start_next_para:
                    start_time = word_info.start_time
                    str_start = timestr.timefm(start_time.seconds +
                                               start_time.nanos * 1e-9)
                    start_next_para = False

                if counter < 10:
                    # when the num of word in this line less than
                    # 10 word, we only add this word in this line
                    line += word
                    if word_index == (punc_index_list[curr]):
                        curr += 1
                        line += punctuation[str(word_index)]
                        word_index += 1
                else:
                    # the line is enouge 10 words, we inster seq num,
                    # time and line into the srt file
                    counter = 0  # clear the counter for nex iteration
                    end_time = word_info.end_time
                    str_end = timestr.timefm(end_time.seconds +
                                             end_time.nanos * 1e-9)
                    writer.write(str(i))  # write the seq num into file,
                    # and then add 1
                    i += 1
                    line += word
                    if word_index == (punc_index_list[curr]):
                        curr += 1
                        line += punctuation[str(word_index)]
                        word_index += 1
                    writer.write('\n')
                    writer.write(str_start)  # write start time
                    writer.write(' --> ')
                    writer.write(str_end)  # write end time
                    writer.write('\n')
                    writer.write(line)  # write the word
                    line = ""  # clear the line for next iteration
                    writer.write('\n\n')
                    start_time = word_info.start_time
                    str_start = timestr.timefm(start_time.seconds +
                                               start_time.nanos * 1e-9)

                # avoid miss any word, because counter < 0,
                # but this iteration has no word remain
                if counter < 10 and num_woeds == 0:
                    end_time = word_info.end_time
                    str_end = timestr.timefm(end_time.seconds +
                                             end_time.nanos * 1e-9)

                    writer.write(str(i))
                    i += 1
                    writer.write('\n')
                    writer.write(str_start)  # write start time
                    writer.write(' --> ')
                    writer.write(str_end)  # write end time
                    writer.write('\n')
                    writer.write(line)  # write the word
                    line = ""
                    writer.write('\n\n')


def main():
    # parse arguments
    # TODO better ... use argparse
    try:
        if sys.argv[1] == "--apikey":
            log(f"setting GOOGLE_APPLICATION_CREDENTIALS from argument: --apikey {sys.argv[2]}")
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sys.argv[2]
            sys.argv = sys.argv[0:1] + sys.argv[3:]

        input_video_path = sys.argv[1]
    except Exception:
        log_usage()
        raise

    check_api_key()

    output_path = './output/'
    if not os.path.exists(output_path):
        os.mkdir(output_path)

    try:
        if input_video_path.startswith('gs://'):
            transcribe_gcs(input_video_path)
        else:
            transcribe_file(input_video_path)
        log("Transcribe done")
    except BaseException as e:
        log('error: transcribe failed!', e)
        raise


if __name__ == "__main__":
    main()
