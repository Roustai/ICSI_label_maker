import sys
import os
import re
import glob
import errno
import argparse

#This is for going through the document and searching for start time, endtime, and speaker
def line_search(lines):
    start = re.search('starttime=(.*)end', lines).group(1)
    start = start.split()[0]
    end = re.search('endtime=(.*) ', lines).group(1)
    end = end.split()[0]
    speaker = re.search('participant=(.*)>', lines)
    if speaker != None:
        return start, end, speaker.group(1)
    else:
        pass

def dial_acts(file_location):
    with open(file_location, 'r') as t:
        text = t.read()

    #locate data after the href= value
    hits = []
    for lines in text.split('\n'):
        hit = re.search('href=(.*)$',lines)
        if hit != None:
            hits.append(hit.group(1).strip('"/>'))

    #split the data based off of the '#' delimeter
    file = [0] * len(hits)
    dial = [0] * len(hits)
    for i, phrase in enumerate(hits):
        file[i], dial[i] = phrase.split('#')
        dial[i] = dial[i].replace('id(', '').replace(')', '')

    #Extend out the dialgoue act, i.e. 209..214 becomes 209, 210, 211, 212, 213, 214
    for i, acts in enumerate(dial):
        if '..' in acts:
            act_beg, act_end = acts.split('..')
            splits = act_beg.partition('act')
            act = splits[0] + splits[1]
            begin = int(splits[2])
            end = int(act_end.partition('act')[2])
            dial[i] = act + str(begin)
            for j in range(begin+1, end+1):
                dial.append(act + str(j))

    key = list(set(file))
    file_name = key[0].split('.')[0]

    #key.sort() #Not necessary but makes the data a lot easier to read
    info = dict.fromkeys(key, 1)

    for keys in key:
        temp = []
        split_one = keys.split('.dial')[0]
        for items in dial:
            if split_one in items:
                temp.append(items)
        info.update({keys : temp})

    return info, file_name

def data_search(args, data_file):
    for key in data_file:
        file_location = args + '/ICSIplus/DialogueActs/' + key

        with open(file_location, 'r') as t:
            text = t.read()

        #Here we create a nested dictionary, its output will look like
        #file_name{dialogue_act {start time, end time, speaker}}
        act_info = {}
        for lines in text.split('\n'):
            for i in range(len(data_file[key])):
                if data_file[key][i] in lines:
                    start, end, speaker = line_search(lines)
                    act_info.update({data_file[key][i] : {'start' : start.replace('"', ''),
                                                          'end' : end.replace('"', ''),
                                                          'speaker' : speaker}})
        data_file.update({key : act_info})
    return(data_file)

def data_match(args, file_name, data):
    location = args + '/ICSI_original_transcripts/transcripts/' + file_name + '.mrt'
    with open(location, 'r') as t:
        text = t.read()

    #The goal here is to remove all un-needed tags
    tags = []
    for item in text.split('\n'):
        if '<S' not in item:
            if '<' in item:
                a = re.findall('<[^>]+>', item)
                for i in range(len(a)):
                    tags.append(a[i])

    # Here we remove the Segment tags from the list of un-needed tags
    tags = list(set(tags))
    if '</Segment>' in tags: tags.remove('</Segment>')
    if '<Segment>' in tags: tags.remove('<Segment>')
    for emphasis_tag in tags:
        text = text.replace(emphasis_tag, '')

    #Here we will go through and pull out every dialogue piece,
    #and set the ground truth label to 0
    full_data = []
    for lines in text.split('\n'):
        #labels vary between the two files, to create uniformity, the tags are all
        #changed to lower case. In addition to this an additional tag is present
        #that must be stripped from the document
        lines = lines.lower()
        if ('participant=' in lines) and ('closemic=' not in lines):
            start, end, speaker = line_search(lines)
            full_data.append([start, end, speaker, 0])
        if ('participant=' in lines) and ('closemic=' in lines):
            lines = lines.replace(' closemic="false"', '')
            start, end, speaker = line_search(lines)
            full_data.append([start, end, speaker, 0])

    #Here we get the items that will be used for generating positive labels
    dial_data = []
    for _, elem in data.items():
        for _, items in elem.items():
            dial_data.append([float(items['start']),
                             float(items['end']),
                             items['speaker']])

    #Here the values are checked to see if the info in dial_data is present
    #in the full data, and to see if it meets the requirements to be positive
    #in that there should be an overlap, like in the text below
    #           all_data_ST <dial_data_ST < all_data_ET
    #                           or
    #           all_data_ST <dial_data_ET < all_data_ET
    for i in range(len(dial_data)):
        for j in range(len(full_data)):
            if full_data[j][2] == dial_data[i][2]:
                fds_time = float(full_data[j][0].replace('"', ''))
                fde_time = float(full_data[j][1].replace('"', ''))
                if (fds_time <= dial_data[i][0] <= fde_time) or \
                        (fds_time <= dial_data[i][1] <= fde_time):
                    full_data[j][3] = 1


    #Now we will go through the document and locate the text file
    #associated with it
    ground_truth = []
    for i in full_data:
        segment = 'StartTime=' +i[0] +' EndTime='+i[1] +' Participant='+ i[2]
        seg_find = re.search(segment+'[^<]*', text)
        if seg_find != None:
            seg_find =seg_find.group().strip(segment)
            seg_find =seg_find.strip('CloseMic="false">')
            seg_find = seg_find.strip()
            if seg_find != '':
                ground_truth.append([i[2], seg_find, i[3]])
    return ground_truth

def create_file(args, file_name, ground_truth):
    dir_name = args + '/place_holder/'
    if not os.path.exists(os.path.dirname(dir_name)):
        try:
            os.makedirs(os.path.dirname(dir_name))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

    f = open(args + '/place_holder/' + file_name + '.tsv', 'w+')
    #f = open(file_name +'test' + '.tsv', 'w+')
    for i in range(len(ground_truth)):
        f.write(str(ground_truth[i][0]) + '::\t' + str(ground_truth[i][1]) + '::\t' + str(ground_truth[i][2]) + '\n')

def main():
    args = sys.argv[1]
    file_list = glob.glob(args + "/ICSIplus/Contributions/Summarization/extractive/*.extsumm.xml")
    if(len(file_list) == 0):
        print("ERROR: Incorrect Directory")
        exit()


    for files in file_list:
        print("file:", files)
        initial_data, file_name = dial_acts(files)
        data_dict = data_search(args, initial_data)
        data_info = data_match(args, file_name, data_dict)
        create_file(args, file_name, data_info)

if __name__ == "__main__":
    main()