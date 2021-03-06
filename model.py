"""Keras Behavioral Cloning model.
"""
import h5py
import json

import cv2
import math
import numpy as np

import keras
from keras.models import Sequential

from keras.layers import Dense, Dropout, Activation, Flatten, Lambda
from keras.layers import Convolution2D, MaxPooling2D, AveragePooling2D
from keras.layers.normalization import BatchNormalization
from keras.regularizers import l1, l2

from keras.optimizers import SGD
from keras.utils import np_utils
from keras.utils.io_utils import HDF5Matrix

from image_preprocessing import ImageDataGenerator


# General parameters.
BATCH_SIZE = 4
LEARNING_RATE = 0.0001
DECAY = 1e-6
BN_EPSILON = 1e-6
NB_EPOCHS = 100.
ANGLE_KEY = 'angle_med10'
ANGLE_WEIGHT = 10.0
L2_WEIGHT = 0.00001
SEED = 4242

FINE_TUNE = 'logs/model.h5'
# FINE_TUNE = None

# Color preprocessing.
BRIGHTNESS_DELTA = 80. / 255.
CONTRAST_LOWER = 0.3
CONTRAST_UPPER = 1.7
SATURATION_LOWER = 0.3
SATURATION_UPPER = 1.7
HUE_DELTA = 0.2

# Image dimensions
IMG_ROWS, IMG_COLS = 160, 320
IMG_ROWS, IMG_COLS = 105, 320
IMG_CHANNELS = 3

# Datasets to use
DATASETS = [
            ('./data/q3_recover_left/dataset.npz', 'angle_med6'),
            ('./data/q3_recover_right/dataset.npz', 'angle_med6'),
            ('./data/q3_recover_left2/dataset.npz', 'angle_med6'),
            ('./data/q3_recover_right2/dataset.npz', 'angle_med6'),
            ('./data/q3_clean/dataset.npz', 'angle_med10'),
            ('./data/q3_clean2/dataset.npz', 'angle_med10'),
           ]


# ============================================================================
# Load data
# ============================================================================
def np_shuffle_pair(x, y):
    rng_state = np.random.get_state()
    np.random.shuffle(x)
    np.random.set_state(rng_state)
    np.random.shuffle(y)


def load_npz(datasets, split=0.9):
    """Load data from Numpy .npz files and rescale images to [0, 1].

    Args:
      filenames: List of dataset: (filename, angle_key).
      split: Split proportion between train / validation datasets.
    Return:
      (X_train, y_train, X_test, y_test) Numpy arrays.
    """
    # Load data from numpy files.
    images = None
    angle = None
    for path, angle_key in datasets:
        print('Loading dataset:', path)
        data = np.load(path)
        if images is None:
            images = data['images'].astype(np.float16)
            angle = data[angle_key]
        else:
            # Resize images and append data.
            shape = images.shape
            new_shape = (shape[0] + data['images'].shape[0], *shape[1:])
            images.resize(new_shape)
            # Image and angle...
            images[shape[0]:, ...] = data['images']
            angle = np.append(angle, data[angle_key], axis=0)

        del data

    # Images and angle pre-processing.
    images /= 255.
    # delta = 6
    # angle = angle[delta:]
    # angle = np.lib.pad(angle, ((0, delta)), 'symmetric')

    # Random shuffling of the dataset (in-place)
    np.random.seed(SEED)
    np_shuffle_pair(images, angle)

    # Split datasets.
    if split < 1.0:
        idx = int(images.shape[0] * split)
        return (images[:idx], angle[:idx],
                images[idx:], angle[idx:])
    else:
        return (images, angle, None, None)


def save_hyperparameters(ckpt_path):
    """Save hyper-parameters in json file.
    """
    hyperparams = {
        'NB_EPOCHS': NB_EPOCHS,
        'BATCH_SIZE': BATCH_SIZE,
        'LEARNING_RATE': LEARNING_RATE,
        'DECAY': DECAY,
        'L2_WEIGHT': L2_WEIGHT,
        'BN_EPSILON': BN_EPSILON,
        'ANGLE_KEY': ANGLE_KEY,
        'ANGLE_WEIGHT': ANGLE_WEIGHT,
        'IMAGE_SIZE': (IMG_ROWS, IMG_COLS),
        'PRE-PROCESSING': {
            'BRIGHTNESS_DELTA': BRIGHTNESS_DELTA,
            'CONTRAST_LOWER': CONTRAST_LOWER,
            'CONTRAST_UPPER': CONTRAST_UPPER,
            'SATURATION_LOWER': SATURATION_LOWER,
            'SATURATION_UPPER': SATURATION_UPPER,
            'HUE_DELTA': HUE_DELTA
        }
    }
    print('Hyper-parameters: ', hyperparams)
    with open(ckpt_path + 'hyperparameters.json', 'w') as f:
        json.dump(hyperparams, f,
                  indent=4, separators=(',', ': '), sort_keys=True)


# ============================================================================
# Model and training
# ============================================================================
def cnn_model(shape):
    """Create the model learning the behavioral cloning from driving data.
    Inspired by NVIDIA paper on this topic.
    """
    model = Sequential()

    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.9999, input_shape=shape))
    # First 5x5 convolutions layers.
    model.add(Convolution2D(24, 5, 5,
                            subsample=(2, 2),
                            W_regularizer=l2(L2_WEIGHT),
                            # init='normal',
                            # input_shape=shape,
                            bias=False,
                            border_mode='valid'))
    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    model.add(Activation('relu'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    # model.add(MaxPooling2D(pool_size=(2, 2), strides=(2, 2), border_mode='same'))
    print('Layer 1: ', model.layers[-1].output_shape)

    model.add(Convolution2D(36, 5, 5,
                            subsample=(2, 2),
                            W_regularizer=l2(L2_WEIGHT),
                            # init='normal',
                            bias=False,
                            border_mode='valid'))
    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    model.add(Activation('relu'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    # model.add(MaxPooling2D(pool_size=(2, 2), strides=(2, 2), border_mode='same'))
    print('Layer 2: ', model.layers[-1].output_shape)

    # model.add(Convolution2D(48, 5, 5,
    #                         subsample=(2, 2),
    #                         # init='normal',
    #                         border_mode='valid'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    # model.add(Activation('relu'))
    # model.add(MaxPooling2D(pool_size=(3, 3), strides=None, border_mode='valid'))
    # print('Layer 3: ', model.layers[-1].output_shape)

    model.add(Convolution2D(54, 5, 5,
                            subsample=(2, 2),
                            # init='normal',
                            W_regularizer=l2(L2_WEIGHT),
                            bias=False,
                            border_mode='valid'))
    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    model.add(Activation('relu'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    # model.add(MaxPooling2D(pool_size=(2, 2), strides=(2, 2), border_mode='same'))

    print('Layer 3: ', model.layers[-1].output_shape)

    model.add(Convolution2D(54, 5, 5,
                            # subsample=(2, 2),
                            # init='normal',
                            W_regularizer=l2(L2_WEIGHT),
                            bias=False,
                            border_mode='valid'))
    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    model.add(Activation('relu'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    print('Layer 3b: ', model.layers[-1].output_shape)

    # 3x3 Convolutions.
    model.add(Convolution2D(64, 3, 3,
                            # init='normal',
                            W_regularizer=l2(L2_WEIGHT),
                            bias=False,
                            border_mode='valid'))
    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    model.add(Activation('relu'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    print('Layer 4: ', model.layers[-1].output_shape)

    model.add(Convolution2D(80, 3, 3,
                            # init='normal',
                            W_regularizer=l2(L2_WEIGHT),
                            bias=False,
                            border_mode='valid'))
    model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    model.add(Activation('relu'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    print('Layer 5: ', model.layers[-1].output_shape)

    # model.add(Convolution2D(96, 3, 3,
    #                         # init='normal',
    #                         border_mode='valid'))
    # model.add(BatchNormalization(epsilon=BN_EPSILON, momentum=0.999))
    # model.add(Activation('relu'))
    # print('Layer 6: ', model.layers[-1].output_shape)

    # Flatten + FC layers.
    model.add(Flatten())
    # model.add(Dense(1000))
    # model.add(Activation('relu'))
    model.add(Dropout(0.5))

    # model.add(Dense(1000, W_regularizer=l2(L2_WEIGHT)))
    # # model.add(BatchNormalization(mode=1, epsilon=BN_EPSILON, momentum=0.999))
    # # model.add(Activation('relu'))
    # # model.add(keras.layers.advanced_activations.ELU(alpha=1.0))
    # model.add(keras.layers.advanced_activations.PReLU())

    model.add(Dense(100, W_regularizer=l2(L2_WEIGHT)))
    # model.add(BatchNormalization(mode=1, epsilon=BN_EPSILON, momentum=0.999))
    # model.add(Activation('relu'))
    # model.add(keras.layers.advanced_activations.ELU(alpha=1.0))
    model.add(keras.layers.advanced_activations.PReLU())
    model.add(Dropout(0.5))

    model.add(Dense(50, W_regularizer=l2(L2_WEIGHT)))
    # model.add(BatchNormalization(mode=1, epsilon=BN_EPSILON, momentum=0.999))
    # model.add(Activation('relu'))
    # model.add(keras.layers.advanced_activations.ELU(alpha=1.0))
    model.add(keras.layers.advanced_activations.PReLU())
    # model.add(Dropout(0.5))

    model.add(Dense(10))
    # model.add(BatchNormalization(mode=1, epsilon=BN_EPSILON, momentum=0.999))
    # model.add(Activation('relu'))
    model.add(keras.layers.advanced_activations.PReLU())
    # model.add(keras.layers.advanced_activations.ELU(alpha=1.0))

    model.add(Dense(1))
    return model


def train_model(X_train, y_train, X_test, y_test, ckpt_path='./'):
    """Train the Convolutional Model described by cnn_model.
    Params:
      X_train: training input;
      y_train: training output;
      X_test: validation input;
      y_test: validation output;
      ckpt_path: Path where to save checkpoint files.
    """

    # Training information.
    print('Checkpoint path: ', ckpt_path)
    print(X_train.shape[0], 'train samples')
    print(X_test.shape[0], 'test samples')
    print('X_train shape:', X_train.shape)

    # Training weights: more on large angles.
    y_weights = np.ones_like(y_train) + ANGLE_WEIGHT * np.abs(y_train)

    # CNN Model.
    model = cnn_model(X_train.shape[1:])
    # Fine tuning model?
    if FINE_TUNE:
        print('Fine tuning model:', FINE_TUNE)
        model.load_weights(FINE_TUNE)

    # Train the model using Adam.
    # optimizer = SGD(lr=LEARNING_RATE, decay=DECAY, momentum=0.9, nesterov=True)
    # optimizer = keras.optimizers.RMSprop(lr=LEARNING_RATE, decay=DECAY,
    #                                      rho=0.9, epsilon=1e-08)
    optimizer = keras.optimizers.Adam(lr=LEARNING_RATE, decay=DECAY,
                                      beta_1=0.9, beta_2=0.999, epsilon=1e-08)

    model.compile(optimizer=optimizer,
                  loss='mse',
                  metrics=['mean_absolute_error'])

    # Save model architecture.
    with open(ckpt_path + 'model.json', 'w') as f:
        json.dump(model.to_json(), f)
    with open(ckpt_path + 'model_read.json', 'w') as f:
        json.dump(json.loads(model.to_json()), f,
                  indent=4, separators=(',', ': '))

    # Pre-processing and realtime data augmentation.
    datagen = ImageDataGenerator(
        featurewise_center=False,   # Input mean to 0 over dataset.
        samplewise_center=False,    # Each sample mean to 0.
        featurewise_std_normalization=False,  # Divide inputs by STD of the dataset.
        samplewise_std_normalization=False,   # Divide each input by its STD.
        zca_whitening=False,        # Apply ZCA whitening
        rotation_range=0,           # Randomly rotate images.
        width_shift_range=0.,       # Random shift (fraction of total width).
        height_shift_range=0.,      # Random shift (fraction of total height).
        brightness_delta=BRIGHTNESS_DELTA,
        contrast_lower=CONTRAST_LOWER,
        contrast_upper=CONTRAST_UPPER,
        saturation_lower=SATURATION_LOWER,
        saturation_upper=SATURATION_UPPER,
        hue_delta=HUE_DELTA,
        horizontal_flip=True,       # Random horizontal flip.
        vertical_flip=False)        # Random vertical flip.

    # Compute quantities required for featurewise normalization.
    # (std, mean, and principal components if ZCA whitening is applied)
    # datagen.fit(X_train)

    # Fit the model with batches generated by datagen.flow()
    callbacks = [
        keras.callbacks.TensorBoard(log_dir=ckpt_path,
                                    histogram_freq=0,
                                    write_graph=True,
                                    write_images=True),
        keras.callbacks.ModelCheckpoint(ckpt_path + 'model.{epoch:03d}-{val_loss:.4f}.h5',
                                        monitor='val_loss',
                                        verbose=1,
                                        save_best_only=True,
                                        save_weights_only=True)
        # keras.callbacks.LearningRateScheduler(lamda:x x)
    ]

    model.fit_generator(datagen.flow(X_train, y_train,
                                     batch_size=BATCH_SIZE,
                                     sample_weight=y_weights,
                                     # save_to_dir='./img/',
                                     # save_format='png',
                                     shuffle=True),
                        samples_per_epoch=X_train.shape[0],
                        nb_epoch=NB_EPOCHS,
                        verbose=1,
                        validation_data=(X_test, y_test),
                        callbacks=callbacks,
                        max_q_size=50,
                        nb_worker=16,
                        pickle_safe=True)

    # Save model parameters.
    model.save(ckpt_path + 'model.h5')


def main():
    # filenames = ['./data/7/dataset.npz',
    #              './data/8/dataset.npz']
    # filenames = ['./data/test3/dataset.npz']
    # filenames = ['./data/small_test/dataset.npz']
    # filenames = ['./data/50hz_1/dataset.npz']
    # filenames = [
    #              './data/q3_clean/dataset.npz',
    #              './data/q3_recover_left/dataset.npz',
    #              './data/q3_recover_right/dataset.npz',
    #             ]

    ckpt_path = './logs/'
    # Load dataset.
    (X_train, y_train, X_test, y_test) = load_npz(DATASETS, split=0.9)
    # Save hyper-parameters.
    save_hyperparameters(ckpt_path)
    # Train model.
    train_model(X_train, y_train, X_test, y_test, ckpt_path=ckpt_path)


if __name__ == '__main__':
    main()
