from flask import Flask, escape, request, render_template
import boto3
import os
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
from pprint import pprint

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
images_bucket = os.environ['IMAGES_BUCKET']
albums_table = os.environ['ALBUMS_TABLE']
app = Flask(__name__)

@app.route('/album/<album_id>')
def hello(album_id):
    table = dynamodb.Table(albums_table)
    try:
        response = table.query(KeyConditionExpression=Key('id').eq(album_id))
        pprint(response)
        if (response['Count'] == 0):
            return {'error': 'Album "{}" not found'.format(album_id)}, 404
        else:
            last_version = response['Items'][-1]
            return render_template('album.html', album=last_version)
        print("response: ", response)
    except ClientError as e:
        return {'error': e}, 500

