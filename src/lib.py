import os

import requests

GH_TOKEN = os.environ.get("GH_TOKEN")


def get(url):
    headers = {}
    if GH_TOKEN and url.find("github.com") >= 0:
        headers["Authorization"] = f"token {GH_TOKEN}"
    req = requests.get(url, headers=headers)
    if not req.ok:
        raise Exception(req.text)
    return req


def post(url, body, headers={}):
    if GH_TOKEN and url.find("github.com") >= 0:
        headers["Authorization"] = f"token {GH_TOKEN}"
    req = requests.post(url, data=body, headers=headers)
    if not req.ok:
        raise Exception(req.text)
    return req


def url_from_dsn(dsn, api):
    base_uri, project_id = dsn.rsplit("/", 1)
    # '{BASE_URI}/api/{PROJECT_ID}/{ENDPOINT}/'
    return f"{base_uri}/api/{project_id}/{api}/"
