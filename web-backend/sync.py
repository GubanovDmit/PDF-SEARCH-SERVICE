# coding: utf-8
import json
import argparse
import base64
import os
import glob
import io
import asyncio
import time
import re
from requests import post
from PyPDF2 import PdfFileWriter, PdfFileReader
from pathlib import Path
from elasticsearch import Elasticsearch
from concurrent.futures import ThreadPoolExecutor

my_folder_id = 'b1gcfjsk4iff6ub1luh8'
elasticSearchAddress = 'http://fulltextsearch:9200'
# Функция возвращает IAM-токен для аккаунта на Яндексе. В данный момент не используется


def get_iam_token(oauth_token):
    iam_url = 'https://iam.api.cloud.yandex.net/iam/v1/tokens'
    response = post(iam_url, json={"yandexPassportOauthToken": oauth_token})
    json_data = json.loads(response.text)
    if json_data is not None and 'iamToken' in json_data:
        return json_data['iamToken']
    return None

# Функция отправляет на сервер запрос на распознавание изображения и возвращает ответ сервера.


def request_analyze(vision_url, iam_token, folder_id, image_data, pageNum, is_pdf=False):
    json_body = {
        'folderId': folder_id,
        'analyzeSpecs': [
            {
                'content': image_data,
                'features': [
                    {
                        'type': 'TEXT_DETECTION',
                        'textDetectionConfig': {'languageCodes': ['*']}
                    }
                ],
            }
        ]}

    # check pdf file and add mime_type
    if is_pdf:
        json_body["analyzeSpecs"][0]["mime_type"] = "application/pdf"
    time_waiting = 0
    response = post(vision_url, headers={
                    'Authorization': 'Bearer '+iam_token}, json=json_body)
    return response.text


def extract_values(obj, key):
    """Pull all values of specified key from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
                elif k == key:
                    arr.append(v)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr
    results = extract(obj, arr, key)
    return results


def add_to_elasticSearch(pdfName, page, text_result, es):
    doc = {"text": text_result}
    res = es.index(index=str.lower(pdfName), id=page, body=doc)


def page_indexing(pageNum, vision_url, iam_token, folder_id, es, pdfname):   
    if str(pageNum).isnumeric():
        print("start work with page ", pageNum, "\n")
        while True:
            NotEmpty = 0
            inputpdf = PdfFileReader(open(str(pageNum) + ".pdf", "rb"))
            for page in range(inputpdf.getNumPages()):
                writer = PdfFileWriter()
                writer.addPage(inputpdf.getPage(page))
                writer.write(open('page.pdf', 'wb'))
                with open('page.pdf', 'rb') as page_pdf:
                    image_data = base64.b64encode(page_pdf.read()).decode('utf-8')
                    response = request_analyze(
                        vision_url, iam_token, folder_id, image_data, pageNum, is_pdf=True)
                    response_json = json.loads(response)
                    text_result = ' '.join(
                        map(str, extract_values(response_json, 'text')))
                    add_to_elasticSearch(pdfname, page, text_result, es)
                    if len(text_result) != 0:
                        NotEmpty = 1
            if(NotEmpty):
                print(pageNum, text_result, "\n")
                break
        time.sleep(0.2)
    else:
        pass


async def index_after_uploading(pdfname):
    inputpdf = PdfFileReader(open(get_link("files", pdfname), "rb"))
    
    for page in range(inputpdf.getNumPages()):
        print(page)
        writer = PdfFileWriter()
        writer.addPage(inputpdf.getPage(page))
        writer.write(open(str(page) + '.pdf', 'wb'))
    
    oauth_token = "AgAAAAADng-8AATuwdOGGyg3l0VHmz1w3Ighmvc"
    iam_token = get_iam_token(oauth_token)
    folder_id = my_folder_id
    #es = Elasticsearch(elasticSearchAddress)
    es = Elasticsearch()
    vision_url = 'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze'
    executor = ThreadPoolExecutor(max_workers=1)
    futures = [
        loop.run_in_executor(executor, page_indexing, pageNum, vision_url,
                           iam_token, folder_id, es, pdfname)
        for pageNum in range(inputpdf.getNumPages())]
    


    answer = page_indexing(inputpdf, vision_url,
                           iam_token, folder_id, es, pdfname)
    awt = await asyncio.gather(*futures)


def search_pages(inputpdf, tags, pdfname):
    #es = Elasticsearch(elasticSearchAddress)
    es = Elasticsearch()
    query_from_user = ' '.join(tags)
    res = es.search(index=str.lower(pdfname), body={"query": {
        "query_string": {
            "query": query_from_user
        }}})
    more_appropriate_page = {}
    for hit in res['hits']['hits']:
        more_appropriate_page[hit["_score"]] = [pdfname,hit["_id"]]
    # pages = []
    # for hit in res['hits']['hits']:
    #     pages.append({int(hit["_id"]): hit["_score"]})
    print('res___ :  ' + str(res))
    print('more_appr:   ' + str(more_appropriate_page) + '  ' + str(tags))
    return more_appropriate_page



# def search_pages(inputpdf, tags, pdfname):
#     # my private data
#     oauth_token = "AgAAAAADng-8AATuwdOGGyg3l0VHmz1w3Ighmvc"
#     iam_token = get_iam_token(oauth_token)
#     folder_id = my_folder_id
#     es = Elasticsearch()
#     vision_url = 'https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze'
#     answer = page_indexing(inputpdf, vision_url,
#                            iam_token, folder_id, es, pdfname)
#     query_from_user = ' '.join(tags)
#     res = es.search(index=str.lower(pdfname), body={"query": {
#         "query_string": {
#             "query": query_from_user
#         }}})
#     more_appropriate_page = {}
#     for hit in res['hits']['hits']:
#         more_appropriate_page[hit["_score"]] = [pdfname,hit["_id"]]
#     # pages = []
#     # for hit in res['hits']['hits']:
#     #     pages.append({int(hit["_id"]): hit["_score"]})
#     print('res___ :  ' + str(res))
#     print('more_appr:   ' + str(more_appropriate_page) + '  ' + str(tags))
#     return more_appropriate_page



def search_across_specific_docs(tags, component_name):
    #es = Elasticsearch(elasticSearchAddress)
    es = Elasticsearch()
    print('component name inside ES:  ' + str(component_name) + ' ' + str(type(component_name)))
    # if component_name:
    #     tags.append(component_name[0].split('_')[0])
    query_from_user = ' '.join(tags)
    indices = es.indices.get_alias("*")  # etract all created indexes
    filtered_indices = {}
    for k, v in indices.items():
        if k.startswith(component_name):
            filtered_indices[k] = v
    print('indices:   ' + str(indices) + ' ' + str(type(indices)))
    print('filtered indices' + str(filtered_indices))
    search_result = {}
    print('query from user:' + str(query_from_user))
    for index in filtered_indices:
        res = es.search(index=index, body={"query": {
            "query_string": {
                "query": query_from_user
            }}})
        pages = []
        for hit in res['hits']['hits']:
            pages.append({int(hit["_id"]): hit["_score"]})
        search_result[index] = pages
    more_appropriate_page = {}
    for index in search_result:
        for pages in search_result[index]:
            for page in pages:
                score = pages[page]
                more_appropriate_page[score] = [index,page]
    return more_appropriate_page


def search_across_all_docs(tags, component_name):
    es = Elasticsearch(elasticSearchAddress)
    print('component name inside ES:  ' + str(component_name) + ' ' + str(type(component_name)))
    if component_name:
        tags.append(component_name)
    query_from_user = ' '.join(tags)
    indices = es.indices.get_alias("*")  # etract all created indexes
    print('indices:   ' + str(indices) + ' ' + str(type(indices)))
    search_result = {}
    print('query from user:' + str(query_from_user))
    for index in indices:
        res = es.search(index=index, body={"query": {
            "query_string": {
                "query": query_from_user
            }}})
        pages = []
        for hit in res['hits']['hits']:
            pages.append({int(hit["_id"]): hit["_score"]})
        search_result[index] = pages
    more_appropriate_page = {}
    for index in search_result:
        for pages in search_result[index]:
            for page in pages:
                score = pages[page]
                more_appropriate_page[score] = [index,page]
    return more_appropriate_page
# # work with absolute links
def get_link(*filename):
    return os.path.join(os.path.dirname(__file__), *filename)

def search_in_download_doc(tags, pdfname):
    inputpdf = PdfFileReader(open(get_link("files", pdfname), "rb"))
    
    pages = search_pages(inputpdf, tags, pdfname)
    return pages


#inputpdf = PdfFileReader(open("Infineon-UserManual_ClassD_audio_MA120xxx_referenc-1609250.pdf", "rb"))
tags = ["development", "V"]
pdfname = "TestDoc.pdf"

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(index_after_uploading(pdfname))
    #delete trash
    res = [f for f in os.listdir() if re.search(r'[-+]?\d+', f)]
    for f in res:
        os.remove(f)
    #loop = asyncio.get_event_loop()
    #loop.run_until_complete(search_in_download_doc(inputpdf,tags,pdfname))