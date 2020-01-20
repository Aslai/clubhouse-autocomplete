import json
import math
import os
import threading
import time

import requests

from pygls.features import COMPLETION
from pygls.server import LanguageServer
from pygls.types import (Position, Range, TextEdit, CompletionItem, CompletionList, CompletionParams)



class ClubhouseLanguageServer(LanguageServer):
    def __init__(self):
        super().__init__()


clubhouse_server = ClubhouseLanguageServer()

clubhouse_token = os.getenv('CLUBHOUSE_API_TOKEN')
clubhouse_url = 'https://api.clubhouse.io'

def cache(key, function, arguments=(), max_age=60*10):
    fname = '/tmp/py-cache-clubhouse-{}.json'.format(key)
    def refresh_cache(function, arguments):
        data = function(*arguments)
        with open(fname, 'w') as f:
            json.dump(data, f)
        return data
    try:
        stats = os.stat(fname)
        now = time.time()
        age = now - stats.st_mtime
        with open(fname, 'r') as f:
            data = json.load(f)
        if age > max_age:
            t = threading.Thread(target=refresh_cache, args=(function, arguments))
            t.start()
        return data
    except:
        return refresh_cache(function, arguments)


def stories_by_type(story_type):
    data = {
        'story_type': story_type
    }
    headers = {'Content-Type': 'application/json'}
    r = requests.post('{}/api/v3/stories/search?token={}'.format(clubhouse_url, clubhouse_token), data=json.dumps(data), headers=headers)
    r.raise_for_status()
    return r.json()

def get_self():
    headers = {'Content-Type': 'application/json'}
    r = requests.get('{}/api/v3/member?token={}'.format(clubhouse_url, clubhouse_token), headers=headers)
    r.raise_for_status()
    return r.json()

def get_workflows():
    headers = {'Content-Type': 'application/json'}
    r = requests.get('{}/api/v3/workflows?token={}'.format(clubhouse_url, clubhouse_token), headers=headers)
    r.raise_for_status()
    return r.json()

def get_epics():
    headers = {'Content-Type': 'application/json'}
    r = requests.get('{}/api/v3/epics?token={}'.format(clubhouse_url, clubhouse_token), headers=headers)
    r.raise_for_status()
    return r.json()



clubhouse_main_workflows = ['engineering', 'deployment']
clubhouse_self = cache('self', get_self, max_age=60*60*24)
all_workflows = cache('workflows', get_workflows, max_age=60*60)
workflow_by_state_id = {}
for workflow in all_workflows:
    for workflow_state in workflow['states']:
        workflow_by_state_id[workflow_state['id']] = {
            'workflow': workflow,
            'state': workflow_state
        }

all_epics = cache('epics', get_epics, max_age=60**60)
epic_by_id = {}
for epic in all_epics:
    epic_by_id[epic['id']] = {
        'epic': epic,
        'namesake': None
    }

all_stories = []
max_story_position = 0
def add_stories(stories):
    global max_story_position
    for story in stories:
        workflow = workflow_by_state_id[story['workflow_state_id']]
        if story['position'] > max_story_position:
            max_story_position = story['position']

        is_namesake = False

        if story['epic_id'] != None and epic_by_id[story['epic_id']]['epic']['name'].lower() == story['name'].lower():
            epic_by_id[story['epic_id']]['namesake'] = story
            is_namesake = True
        
        all_stories.append({
            'story': story,
            'is_mine': clubhouse_self['id'] in story['owner_ids'],
            'in_progress': workflow['state']['type'].lower() == 'started',
            'main_workflow': workflow['workflow']['name'].lower() in clubhouse_main_workflows,
            'is_namesake': is_namesake
        })


add_stories(cache('story-feature', stories_by_type, ('feature',)))
add_stories(cache('story-bug', stories_by_type, ('bug',)))
add_stories(cache('story-chore', stories_by_type, ('chore',)))

@clubhouse_server.feature(COMPLETION)
def completions(ls, params: CompletionParams = None):
    print ('start')
    ls.show_message('Validating ' + str(params.position.character))
    if params.position.character < 3:
        print ('end')
        return 
    document = ls.workspace.get_document(params.textDocument.uri)
    lines = document.lines
    line = lines[params.position.line]
    idx = line.rfind('[ch', 0, params.position.character)
    #print(line)
    if idx == -1:
        print ('end')
        return
    next_char = ''
    if params.position.character + 1 < len(line):
        next_char = line[params.position.character + 1]
    if next_char != ']':
        next_char = ']'
    else:
        next_char = ''
    in_list = False
    list_head = line[:idx]
    line = line[idx:params.position.character]
    list_bullet = list_head.replace(' ', '')
    list_stories = []
    first_list_head = list_head
    insert_epic_after = -1
    if list_bullet in ['*', '-']:
        in_list = True
        def extract_id(search_line: str):
            line = search_line[1:] # trim the bullet
            if not line.startswith('[ch'):
                return None
            line = line[3:] # Skip `[ch`
            idx = line.find(']')
            if idx == -1:
                return None
            line = line[:idx]
            try:
                return int(line)
            except:
                return None
            

        first_line = params.position.line
        search_line = lines[first_line].replace(' ', '')
        while first_line > 0 and search_line.startswith(list_bullet):
            first_line -= 1
            search_line = lines[first_line].replace(' ', '')
            story_id = extract_id(search_line)
            if story_id != None:
                list_stories.append(story_id)
        first_line += 1
        first_list_head = lines[first_line]
        idx = first_list_head.find('[')
        first_list_head = first_list_head[:idx]

        insert_epic_after = first_line
        last_line = params.position.line
        search_line = lines[last_line].replace(' ', '')
        while last_line + 1 < len(lines) and search_line.replace(' ', '').startswith(list_bullet):
            last_line += 1
            search_line = lines[last_line].replace(' ', '')
            story_id = extract_id(search_line)
            if story_id != None:
                list_stories.append(story_id)
        


    if line.find(']') != -1:
        print ('end')
        return
    line = line[3:]

    print(line)

    items = []
    prec = math.ceil(math.log10(max_story_position))
    sort_str = '{}:0{}d{}'.format('{', prec, '}')
    ordering = 0

    prefix = '{}'.format(line)
    try:
        id = int(line)
    except:
        prefix = ''

    comp_items = []
    for item in all_stories:
        story = item['story']
        if prefix != '':
            if not str(story['id']).startswith(prefix):
                continue

        tag = 'ch{}'.format(story["id"])
        label = tag
        detail = tag + ': ' 
        if item['is_namesake']:
            detail += 'Epic: '
        detail += story["name"]
        cap = 94
        sort_text = ''
        def sort_conf(is_higher_prio):
            if is_higher_prio:
                return '('
            return '['
        sort_text += sort_conf(item['main_workflow'])
        sort_text += sort_conf(item['in_progress'])
        sort_text += sort_conf(item['is_mine'])
        sort_text += sort_str.format(story['position'])
        insert_text = tag + next_char
        epic_insert = []
        kind = 'enumMember'
        if in_list:
            insert_text += ' ' 
            if item['is_namesake']:
                insert_text += 'Epic: '
                kind = 'enum'
            insert_text += story['name'] + '\n' + list_head
            if story['epic_id'] is not None and not item['is_namesake']:
                namesake = epic_by_id[story['epic_id']]['namesake']
                if namesake is not None and namesake['id'] not in list_stories:
                    pos = Position(insert_epic_after, 0)
                    epic_text = '{}[ch{}] Epic: {}\n'.format(first_list_head, namesake['id'], namesake['name'])
                    epic_insert = [TextEdit(Range(pos, pos), epic_text)]


        if len(detail) > cap:
            detail = detail[:cap - 3]+'...'
        
        comp_items.append(CompletionItem(
            label=detail,
            sort_text=sort_text,
            insert_text=insert_text,
            additional_text_edits=epic_insert,
            kind=kind
        ))

    print ('end')
    return CompletionList(False, comp_items)


print("running")

#clubhouse_server.start_io()
clubhouse_server.start_tcp("127.0.0.1", 45141)