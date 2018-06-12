#!/usr/bin/env python
# -*- coding: utf-8 -*-

###############################################################################
#  Copyright Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import os.path
import time

import mock
import pytest

from girder import events
from girder.models.folder import Folder
from girder.models.item import Item
from girder.models.upload import Upload
from girder_client import GirderClient

from girder_plugin_metadata_extractor.metadata_extractor import ClientMetadataExtractor


@pytest.fixture
def hachoirLogger():
    with mock.patch('hachoir_core.log.Log.newMessage') as newMessage:
        yield newMessage


@pytest.fixture
def waitForProcessing(server, hachoirLogger):
    counter = {
        'count': 0
    }

    def postUpload(event):
        counter['count'] += 1

    def wait(count):
        startTime = time.time()
        while time.time()-startTime < 1:
            if counter['count'] >= count:
                break
            time.sleep(0.1)
        assert counter['count'] >= count

    events.bind('data.process', 'metadata_extractor_test', postUpload)
    yield wait
    events.unbind('data.process', 'metadata_extractor_test')


@pytest.fixture
def testData(server, user, fsAssetstore, waitForProcessing):
    folders = Folder().childFolders(user, 'user', user=user)
    publicFolders = [folder for folder in folders if folder['public']]
    assert publicFolders is not None

    name = 'Girder_Favicon.png'
    mimeType = 'image/png'
    item = Item().createItem(name, user, publicFolders[0])

    # fix
    path = os.path.join(os.path.dirname(__file__), 'files', name)

    upload = Upload().createUpload(
        user, name, 'item', item, os.path.getsize(path), mimeType)
    with open(path, 'rb') as fd:
        uploadedFile = Upload().handleChunk(upload, fd)

    for key in ['assetstoreId', 'created', 'creatorId', 'itemId',
                'mimeType', 'name', 'size']:
        assert key in uploadedFile
    waitForProcessing(1)

    name2 = 'small.tiff'
    item2 = Item().createItem(name2, user, publicFolders[0])
    file2 = os.path.join(os.path.dirname(__file__), 'files', 'small.tiff')
    Upload().uploadFromFile(
        open(file2), os.path.getsize(file2), name2, 'item', item2, user)
    waitForProcessing(2)
    yield {
        'item': item,
        'name': name,
        'mimeType': mimeType,
        'path': path
    }


@pytest.mark.plugin('metadata_extractor')
def testServerMetadataExtractor(testData, user):
    startTime = time.time()
    while True:
        item = Item().load(testData['item']['_id'], user=user)
        if 'meta' in item:
            if 'MIME type' in item['meta']:
                break
        if time.time()-startTime > 15:
            break
        time.sleep(0.1)
    assert item['name'] == testData['name']
    assert 'meta' in item
    assert item['meta']['MIME type'] == testData['mimeType']


@pytest.mark.plugin('metadata_extractor')
@pytest.mark.skip('Unsure how to use girder_client in pytest')
def testClientMetadataExtractor(testData, user):
    item = Item().load(testData['item']['_id'], user=user)
    assert item['name'] == testData['name']

    del item['meta']
    item = Item().save(item)
    assert 'meta' not in item

    client = GirderClient('localhost', int(os.environ['GIRDER_PORT']))
    client.authenticate(user['login'], 'password')
    extractor = ClientMetadataExtractor(client, testData['path'], testData['item']['_id'])
    extractor.extractMetadata()
    item = Item().load(testData['item']['_id'], user=user)
    assert item['name'] == testData['name']
    assert 'meta' in item
    assert item['meta']['MIME type'] == testData['mimeType']
