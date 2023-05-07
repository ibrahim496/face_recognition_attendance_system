from flask import Flask, render_template, request, redirect, url_for, escape

import boto3
import os
import mysql.connector
import cv2
import uuid
import base64

# Connect to the MySQL database
db = mysql.connector.connect(
    host='localhost',
    user='root',
    password='khalil4820',
    database='sys',
    auth_plugin='mysql_native_password'
)

app = Flask(__name__)