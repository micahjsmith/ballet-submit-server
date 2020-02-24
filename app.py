import logging
import pathlib
import tempfile
import uuid
from os import getenv
from textwrap import dedent

import ballet.templating
import git
from ballet.util import truthy
from ballet.util.code import blacken_code
from ballet.util.git import set_config_variables
from cookiecutter.utils import work_in
from flask import Flask, request
from flask_cors import CORS
from github import Github
from stacklog import stacklog

app = Flask(__name__)
CORS(app)


app.logger.setLevel(logging.INFO)


USERNAME = 'ballet-demo-user-1'
PASSWORD = getenv('GITHUB_TOKEN')
REPO_NAME = 'ballet-predict-house-prices'
REPO_URL = f'https://{USERNAME}:{PASSWORD}@github.com/{USERNAME}/{REPO_NAME}'
UPSTREAM_REPO_SPEC = f'HDI-Project/{REPO_NAME}'


@app.route('/status')
def status():
    return 'OK'


@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    code_content = data['codeContent']
    pr_url = create_pull_request_for_code_content(code_content)
    return pr_url


def make_feature_and_branch_name():
    my_id = str(uuid.uuid4())
    branch_name = f'submit-feature-{my_id}'

    underscore_id = my_id.replace('-', '_')
    feature_name = f'feature_{underscore_id}'
    return feature_name, branch_name


def get_new_feature_path(changes):
    cwd = pathlib.Path.cwd()
    for (name, kind) in changes:
        if kind == 'file' and '__init__' not in str(name):
            relname = pathlib.Path(name).relative_to(cwd)
            abspath = cwd.joinpath(relname)
            return abspath
    return None


def create_pull_request_for_code_content(code_content):
    if truthy(getenv('DEBUG', default='false')):
        return 'http://some/testing/url'

    with tempfile.TemporaryDirectory() as dirname:
        # clone directory to dir
        with stacklog(app.logger.info, 'Cloning repo'):
            repo = git.Repo.clone_from(REPO_URL, to_path=dirname)

        with work_in(dirname):
            # configure repo
            with stacklog(app.logger.info, 'Configuring repo'):
                set_config_variables(repo, {
                    'user.name': 'Demo1',
                    'user.email': 'ballet-demo-user-1@mit.edu',
                })
                repo.remote().set_url(REPO_URL)

            # create a new branch
            with stacklog(app.logger.info, 'Creating new branch and checking it out'):
                feature_name, branch_name = make_feature_and_branch_name()
                repo.create_head(branch_name)
                repo.heads[branch_name].checkout()

            # start new feature
            with stacklog(app.logger.info, 'Starting new feature'):
                extra_context = {
                    'username': USERNAME,
                    'featurename': feature_name,
                }
                changes = ballet.templating.start_new_feature(no_input=True, extra_context=extra_context)
                changed_files = [
                    str(pathlib.Path(name).relative_to(dirname))
                    for (name, kind) in changes
                    if kind == 'file'
                ]
                new_feature_path = get_new_feature_path(changes)

            # add code content to path
            with stacklog(app.logger.info, 'Adding code content'):
                with open(new_feature_path, 'w') as f:
                    blackened_code_content = blacken_code(code_content)
                    f.write(blackened_code_content)

            # commit new code
            with stacklog(app.logger.info, 'Committing new feature'):
                repo.index.add(changed_files)
                repo.index.commit('Add new feature')

            # push to branch
            with stacklog(app.logger.info, 'Pushing to remote'):
                refspec = f'refs/heads/{branch_name}:refs/heads/{branch_name}'
                repo.remote().push(refspec=refspec)

            # create pull request
            with stacklog(app.logger.info, 'Creating pull request'):
                github = Github(PASSWORD)
                grepo = github.get_repo(UPSTREAM_REPO_SPEC)
                title = 'Propose new feature'
                body = dedent(f'''\
                    Propose new feature: {feature_name}
                    Submitted by user: {USERNAME}

                    --
                    Pull request automatically created by ballet-submit-server
                ''')
                base = 'master'
                head = f'{USERNAME}:{branch_name}'
                maintainer_can_modify = True
                app.logger.debug(f'About to create pull: title={title}, body={body}, base={base}, head={head}')
                pr = grepo.create_pull(title=title, body=body, base=base, head=head,
                                       maintainer_can_modify=maintainer_can_modify)
                return pr.html_url
