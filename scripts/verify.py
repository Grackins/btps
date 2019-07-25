#!/usr/bin/python

import sys
import os
import json
import subprocess

from color_util import colored, cprint, colors

BASE_DIR = os.environ.get('BASE_DIR')
PROBLEM_NAME = os.environ.get('PROBLEM_NAME')
HAS_GRADER = os.environ.get('HAS_GRADER')
HAS_MANAGER = os.environ.get('HAS_MANAGER')
WEB_TERMINAL = os.environ.get('WEB_TERMINAL')

#TODO read these 2 variables from problem.json
java_enabled = True
pascal_enabled = False

valid_problem_types = ('Batch', 'Communication', 'OutputOnly', 'TwoSteps')
model_solution_verdict = 'model_solution'
valid_verdicts = (model_solution_verdict, 'correct', 'time_limit', 'memory_limit', 'incorrect', 'runtime_error', 'failed', 'time_limit_and_runtime_error', 'partially_correct')
necessary_files = (
    'checker/testlib.h', 'checker/Makefile', 'checker/checker.cpp',
    'validator/testlib.h', 'validator/Makefile',
    'gen/testlib.h', 'gen/Makefile', 'gen/data',
)

grader_necessary_files = [
    'grader/cpp/%s.h' % PROBLEM_NAME, 'grader/cpp/grader.cpp',
]
if java_enabled:
    grader_necessary_files.append('grader/java/grader.java')
if pascal_enabled:
    grader_necessary_files.append('grader/pas/grader.pas')

manager_necessary_files = (
    'grader/Makefile', 'grader/manager.cpp'
)

if sys.version_info >= (3,):
    string_types = (str,)
else:
    string_types = (str, unicode)

errors = []
warnings = []
namespace = ''


def error(description):
    errors.append('ERROR: {} - {}'.format(namespace, description))


def warning(description):
    warnings.append('WARNING: {} - {}'.format(namespace, description))


def check_keys(data, required_keys, json_name=None):
    key_not_found = False
    for key in required_keys:
        if key not in data:
            if json_name:
                error('{} is required in {}'.format(key, json_name))
            else:
                error('{} is required'.format(key, json_name))
            key_not_found = True
    if key_not_found:
        raise KeyError


def error_on_duplicate_keys(ordered_pairs):
    data = {}
    for key, value in ordered_pairs:
        if key in data:
            error("duplicate key: {}".format(key))
        else:
            data[key] = value
    return data


def load_data(json_file, required_keys=()):
    try:
        with open(json_file, 'r') as f:
            try:
                data = json.load(f, object_pairs_hook=error_on_duplicate_keys)
            except ValueError:
                error('invalid json')
                return None
    except IOError:
        error('file does not exists')
        return None
    try:
        check_keys(data, required_keys)
    except KeyError:
        return None
    return data

def is_ignored(file_name):
    return any(file_name.endswith(ending) for ending in ['.exe', '.class', '~']) 

def get_list_of_files(directory):
    return [file for file in os.listdir(directory) if not is_ignored(file)]


def verify_problem():
    problem = load_data(os.path.join(BASE_DIR, 'problem.json'), ['name', 'title', 'type', 'time_limit', 'memory_limit'])
    if problem is None:
        return problem

    if not isinstance(problem['name'], string_types):
        error('name is not a string')
    elif WEB_TERMINAL is None or WEB_TERMINAL != "true":
        # TODO check if git is available
        # TODO handle it with less bash
        git_origin_name = subprocess.check_output('bash -c "basename $(git config --local remote.origin.url)"', shell=True).strip().decode('utf-8')[:-4]
        if problem['name'] != git_origin_name:
            warning('problem name and git project name are not the same')

    if not isinstance(problem['title'], string_types):
        error('title is not a string')

    try:
        with open(os.path.join(BASE_DIR, 'statement', 'index.md')) as f:
            first_line = None
            for line in f.readlines():
                if line.strip() != '':
                    first_line = line
                    break

            if first_line is None:
                warning('statement is empty')
            elif not first_line.strip().startswith('#'):
                warning('statement does not start with a title')
            else:
                statement_title = first_line.replace('#', '').strip()
                if statement_title != problem['title']:
                    warning('title (%s) does not match title in statement (%s)' % (problem['title'], statement_title))
    except IOError:
        warning('statement does not exists')

    if not isinstance(problem['type'], string_types) or problem['type'] not in valid_problem_types:
        error('type should be one of {}'.format('/'.join(valid_problem_types)))

    if 'has_grader' in problem:
        if not isinstance(problem['has_grader'], bool):
            error('has_grader should be a boolean')
        else:
            if problem['type'] == 'OutputOnly' and problem['has_grader'] is True:
                warning('output only problems could not have grader')

    if 'has_manager' in problem:
        if not isinstance(problem['has_manager'], bool):
            error('has_manager should be a boolean')
        else:
            if problem['type'] == 'Communication' and problem['has_manager'] is False:
                warning('communication problems must have manager')
            if problem['type'] == 'OutputOnly' and problem['has_manager'] is True:
                warning('output only problems could not have manager')

    if not isinstance(problem['time_limit'], float) or problem['time_limit'] < 0.5:
        error('time_limit should be a number greater or equal to 0.5')

    memory = problem['memory_limit']
    if not isinstance(memory, int) or memory < 1 or memory & (memory - 1) != 0:
        error('memory_limit should be an integer that is a power of two')

    return problem


def verify_subtasks():
    subtasks_data = load_data(os.path.join(BASE_DIR, 'subtasks.json'), ['subtasks'])
    
    if subtasks_data is None:
        return None

    k_glob = 'global_validators'
    k_sub = 'subtask_sensitive_validators'
    if (k_glob not in subtasks_data) and (k_sub not in subtasks_data):
        error('Neither "{}" nor "{}" is present in "{}".'.format(k_glob, k_sub, 'subtasks.json'))
        return None
    
    validator_files = list(set(get_list_of_files(os.path.join(BASE_DIR, 'validator/'))) - {'testlib.h', 'Makefile'})
    used_validators = set()

    def check_validator_key(parent, key, name, parName=None):
        if key not in parent:
            return
        validators_list=parent[key]
        parLoc = '' if parName is None else ' in "{}"'.format(parName)
        if not isinstance(validators_list, list):
            error('"{}" is not an array{}'.format(key, parLoc))
            return
        for index, validator_cmd_line in enumerate(validators_list):
            if not isinstance(validator_cmd_line, string_types):
                error('{} validator #{} is not a string{}'.format(name, index+1, parLoc))
                continue
            validator_cmd = validator_cmd_line.split(' ')[0]
            if '.' in validator_cmd:
                if validator_cmd not in validator_files:
                    error('File not found for {} validator "{}"{}'.format(name, validator_cmd, parLoc))
                else:
                    used_validators.add(validator_cmd)

    
    check_validator_key(subtasks_data, k_glob, 'global')
    check_validator_key(subtasks_data, k_sub, 'subtask-sensitive')
    
    subtask_placeholder_var = "subtask"
    subtask_placeholder_substitute = "___SUBTASK_PLACEHOLDER_SUBSTITUTE___"
    for subtask_sensitive_validator in subtasks_data.get(k_sub, []):
        try:
            subtask_validator_substituted = subtask_sensitive_validator.format(**{
                    subtask_placeholder_var : subtask_placeholder_substitute
                })
        except KeyError as e:
            error('Subtask-sensitive validator "{}" contains unknown placeholder {{{}}}.'.format(subtask_sensitive_validator, e.args[0]))
        else:
            if subtask_placeholder_substitute not in subtask_validator_substituted:
                error('Subtask-sensitive validator "{}" does not contain the subtask placeholder {{{}}}.'.format(subtask_sensitive_validator, subtask_placeholder_var))
    

    subtasks = subtasks_data['subtasks']
    hasSamples = False
    try:
        if problem['type'] != 'OutputOnly':
            check_keys(subtasks, ['samples'])
            hasSamples = True
    except KeyError:
        pass

    indexes = set()
    score_sum = 0

    for name, data in subtasks.items():
        if not isinstance(data, dict):
            error('invalid data in {}'.format(name))
            continue

        try:
            check_keys(data, ['index', 'score'], name)
        except KeyError:
            continue

        indexes.add(data['index'])

        if not isinstance(data['score'], int) or data['score'] < 0:
            error('score should be a non-negative integer in subtask {}'.format(name))
        elif name == 'samples':
            if data['score'] != 0:
                error('samples subtask score is non-zero')
        else:
            score_sum += data['score']

        check_validator_key(data, 'validators', 'subtask', name)

    for unused_validator in set(validator_files) - used_validators:
        warning('Unused validator file "{}"'.format(unused_validator))

    if score_sum != 100:
        error('sum of scores is {}'.format(score_sum))

    for i in range(len(subtasks)):
        if i+(0 if hasSamples else 1) not in indexes:
            error('missing index {} in subtask indexes'.format(i))

    return subtasks


def verify_verdict(verdict, key_name):
    if not isinstance(verdict, string_types) or verdict not in valid_verdicts:
        error('{} verdict should be one of {}'.format(key_name, '/'.join(valid_verdicts)))
        return False
    return True


def get_model_solution(solutions):
    for solution, data in enumerate(solutions):
        if isinstance(data, dict) and 'verdict' in data:
            if data['verdict'] == model_solution_verdict:
                return solution


def verify_solutions(subtasks):
    solutions = load_data(os.path.join(BASE_DIR, 'solutions.json'))
    if solutions is None or subtasks is None:
        return solutions

    model_solution = None
    solution_files = set(get_list_of_files(os.path.join(BASE_DIR, 'solution/')))

    for solution in solutions:
        if solution not in solution_files:
            error('{} does not exists'.format(solution))
            continue
        solution_files.remove(solution)

        data = solutions[solution]

        try:
            check_keys(data, ['verdict'], solution)
        except KeyError:
            continue

        verified = verify_verdict(data['verdict'], solution)
        if verified and data['verdict'] == model_solution_verdict:
            if model_solution is not None:
                error('there is more than one model solutions')
            model_solution = solution

        if 'except' in data:
            exceptions = data['except']
            if not isinstance(exceptions, dict):
                error('invalid except format in {}'.format(solution))
            else:
                for subtask_verdict in exceptions:
                    if subtask_verdict not in subtasks:
                        error('subtask "{}" is not defined and cannot be used in except'.format(subtask_verdict))
                    else:
                        verify_verdict(exceptions[subtask_verdict], '{}.except.{}'.format(solution, subtask_verdict))

    if model_solution is None:
        error('there is no model solution')

    for solution in solution_files:
        error('{} is not represented'.format(solution))

    return solutions


def verify_existence(files):
    for file in files:
        if not os.path.isfile(os.path.join(BASE_DIR, file)):
            error(file)


def verify():
    global namespace
    namespace = 'problem.json'
    global problem
    problem = verify_problem()

    namespace = 'subtasks.json'
    subtasks = verify_subtasks()

    namespace = 'solutions.json'
    verify_solutions(subtasks)

    namespace = 'not found'
    verify_existence(necessary_files)
    if HAS_GRADER == "true":
        verify_existence(grader_necessary_files)
    if HAS_MANAGER == "true":
        verify_existence(manager_necessary_files)

    for error in errors:
        cprint(colors.ERROR, error)

    if not errors:
        if warnings:
            print(colored(colors.WARN, "verified,") + " but there are some warnings.")
        else:
            cprint(colors.OK, "verified.")

    for warning in warnings:
        cprint(colors.WARN, warning)


if __name__ == "__main__":
    verify()
