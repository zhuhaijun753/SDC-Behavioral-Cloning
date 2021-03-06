import argparse
import base64
import json

import numpy as np
import socketio
import eventlet
import eventlet.wsgi
import time
from PIL import Image
from PIL import ImageOps
from flask import Flask, render_template
from io import BytesIO

from keras.models import model_from_json
from keras.preprocessing.image import ImageDataGenerator, array_to_img, img_to_array

from skimage import color

sio = socketio.Server()
app = Flask(__name__)
model = None
prev_image_array = None


def image_preprocessing(img):
    img = img.astype(np.float32) / 255.
    # img = 2. * img - 1.

    # Cut bottom and top.
    img = img[55:, :, :]

    # img = color.rgb2hsv(img)
    # img = 2 * img - 1

    # out = cv2.resize(out, (IMG_SHAPE[1], IMG_SHAPE[0]), interpolation=cv2.INTER_LANCZOS4)
    # out = out[34:-10, :, :]
    # out = cv2.cvtColor(out, cv2.COLOR_BGR2HLS)
    return img

@sio.on('telemetry')
def telemetry(sid, data):
    # The current steering angle of the car
    steering_angle = data["steering_angle"]
    # The current throttle of the car
    throttle = data["throttle"]
    # The current speed of the car
    speed = data["speed"]
    # The current image from the center camera of the car
    imgString = data["image"]
    image = Image.open(BytesIO(base64.b64decode(imgString)))
    image_array = np.asarray(image)

    image_array = image_preprocessing(image_array)
    transformed_image_array = image_array[None, :, :, :]

    # This model currently assumes that the features of the model are just the images. Feel free to change this.
    angle_factor = 180. / 25. / np.pi * 1.5
    steering_angle = float(model.predict(transformed_image_array, batch_size=1)) * angle_factor
    # The driving model currently just outputs a constant throttle. Feel free to edit this.
    throttle = 0.5

    print('Steering: %.3f | Throttle: %.3f | Factor: %.3f' % (steering_angle,
                                                              throttle,
                                                              angle_factor))
    send_control(steering_angle, throttle)


@sio.on('connect')
def connect(sid, environ):
    print("connect ", sid)
    send_control(0, 0)


def send_control(steering_angle, throttle):
    sio.emit("steer", data={
        'steering_angle': steering_angle.__str__(),
        'throttle': throttle.__str__()
    }, skip_sid=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Remote Driving')
    parser.add_argument('model', type=str,
        help='Path to model definition json. Model weights should be on the same path.')
    args = parser.parse_args()

    # Model path.
    path = args.model
    root = path.split('.')[0]

    # Load model description
    jpath = root + '.json'
    with open(jpath, 'r') as jfile:
        model = model_from_json(json.load(jfile))

    # Load model weights.
    model.compile("adam", "mse")
    wpath = args.model.replace('json', 'h5')
    model.load_weights(wpath)

    # wrap Flask application with engineio's middleware
    app = socketio.Middleware(sio, app)

    # deploy as an eventlet WSGI server
    eventlet.wsgi.server(eventlet.listen(('', 4567)), app)
