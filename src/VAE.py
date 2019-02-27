# -*- coding: utf-8 -*-
"""
@author: jzh
"""
from keras.layers import Reshape, LeakyReLU, Flatten, Activation, Input, Concatenate, Add
from keras.layers import Dense, Lambda
from keras.models import Model
import keras.backend as K
from keras.engine.topology import Layer

class BiasChanneWise(Layer):
    def __init__(self, **kwargs): 
        super(BiasChanneWise, self).__init__(**kwargs)
    def build(self, input_shape):
        # Create a trainable weight variable for this layer. 
        self.bias = self.add_weight(name='bias',
                            shape=(input_shape[1:]),
                            initializer='zeros',
                            trainable=True)
        super(BiasChanneWise, self).build(input_shape)
    def call(self, x): 
        return x+self.bias
    def compute_output_shape(self, input_shape): 
        return input_shape
    
class Bias(Layer):
    def __init__(self, **kwargs): 
        super(Bias, self).__init__(**kwargs)
    def build(self, input_shape):
        # Create a trainable weight variable for this layer. 
        self.bias = self.add_weight(name='bias',
                            shape=(input_shape[1],1),
                            initializer='zeros',
                            trainable=True)
        super(Bias, self).build(input_shape)
    def call(self, x): 
        return x+self.bias
    def compute_output_shape(self, input_shape): 
        return input_shape
    
def sampling(args):
    """Implements reparameterization trick by sampling
    from a gaussian with zero mean and std=1.
    Arguments:
        args (tensor): mean and log of variance of Q(z|X)
    Returns:
        sampled latent vector (tensor)
    """

    z_mean, z_log_var = args
    batch = K.shape(z_mean)[0]
    dim = K.int_shape(z_mean)[1]
    # by default, random_normal has mean=0 and std=1.0
    epsilon = K.random_normal(shape=(batch, dim))
    return z_mean + K.exp(0.5 * z_log_var) * epsilon
'''
GCN code was inspired by https://github.com/tkipf/keras-gcn
'''
def get_gcn_dis_networks(T_k, support = 3, batch_size = 1, v = 11510, feature_dim = 9, latent_dim_id = 50, latent_dim_exp = 25, hidden_dim = 300,input_dim = 11510 * 9, vis = False):
    g = [K.variable(_) for _ in T_k]
    def gcn(x):
        supports = list()
        for i in range(support):
            num , v , feature_shape = K.int_shape(x)
            LF = list()
            for j in range(batch_size):
                LF.append(K.expand_dims(K.dot(g[i], K.squeeze(K.slice(x, [j,0,0],[1,v,feature_shape]), axis = 0)), axis=0))
            supports.append(K.concatenate(LF,axis=0)) 
        x = K.concatenate(supports)
        return x
    def GConv(x, input_dim, output_dim, support, active_func = LeakyReLU(alpha=0.1)):
        x = Lambda(gcn, output_shape=(v, support*input_dim))(x)
        x = Dense(output_dim)(x)
        x = active_func(x)
        return x
        
        
    #------------------------------
    # Build encoder
    #------------------------------
    
    inputs = Input(shape=(input_dim, ))
    x = inputs
    y = inputs
    x = Reshape((v, feature_dim))(x)
    y = Reshape((v, feature_dim))(y)
    # One GCN Layer
    x = GConv(x, feature_dim, 128, support)
    x = GConv(x, 128, 64, support)
    x = GConv(x, 64, 64, support)
    x = GConv(x, 64, 64, support)
    x = GConv(x, 64, 1, support, Activation('tanh'))
    x = Flatten()(x)

    y = GConv(y, feature_dim, 128, support)
    y = GConv(y, 128, 64, support)
    y = GConv(y, 64, 64, support)
    y = GConv(y, 64, 64, support)
    y = GConv(y, 64, 1, support, Activation('tanh'))
    y = Flatten()(y)
    x = Dense(hidden_dim)(x)
    y = Dense(hidden_dim)(y)
    x=LeakyReLU(alpha=0.1)(x)
    y=LeakyReLU(alpha=0.1)(y)
    z_mean_id = Dense(latent_dim_id, name='z_mean_id')(x)
    z_mean_exp = Dense(latent_dim_exp, name='z_mean_exp')(y)
    x = Activation('sigmoid')(x)
    y = Activation('sigmoid')(y)
    z_log_var_id = Dense(latent_dim_id, name='z_log_var_id')(x)
    z_log_var_exp = Dense(latent_dim_exp, name='z_log_var_exp')(y)
    # use reparameterization trick to push the sampling out as input
    # note that "output_shape" isn't necessary with the TensorFlow backend
    z_id = Lambda(sampling, output_shape=(latent_dim_id,), name='z_id')([z_mean_id, z_log_var_id])
    z_exp = Lambda(sampling, output_shape=(latent_dim_exp,), name='z_exp')([z_mean_exp, z_log_var_exp])

    encoder = Model(inputs, [z_mean_id, z_mean_exp, z_log_var_id,  z_log_var_exp, z_id, z_exp], name = 'encoder')
    encoder_id = Model(inputs, [z_mean_id, z_log_var_id, z_id], name = 'encoder_id')
    encoder_exp = Model(inputs, [z_mean_exp, z_log_var_exp, z_exp], name = 'encoder_exp')
    #----------------------------
    # Build 2 decoder
    #----------------------------
    tensor_id = Input(shape=(latent_dim_id, ))
    x = Dense(hidden_dim)(tensor_id)
    x=LeakyReLU(alpha=0.1)(x)
    x = Dense(input_dim)(x)
    output = Activation('tanh')(x)
    decoder_id = Model(tensor_id,output)
    
    tensor_exp = Input(shape=(latent_dim_exp, ))
    x = Dense(hidden_dim)(tensor_exp)
    x=LeakyReLU(alpha=0.1)(x)
    x = Dense(input_dim)(x)
    output = Activation('tanh')(x)
    decoder_exp = Model(tensor_exp, output)
    #------------------------------
    # Build mixture gcn model
    #------------------------------

    rec_id = Input(shape=(feature_dim * v, ))
    rec_exp = Input(shape=(feature_dim * v, ))
    
    
    x_id = Reshape((v, feature_dim))(rec_id)
    x_exp = Reshape((v, feature_dim))(rec_exp)
    x = Concatenate()([x_id, x_exp])

    
    x = GConv(x, 2*feature_dim, 64, support)
    x = GConv(x, 64, 32, support)
    x = GConv(x, 32, 32, support)
    x = GConv(x, 32, 16, support)
    x = GConv(x, 16, feature_dim, support)

    
    x = Reshape((feature_dim*v,))(x)
    #x = Bias()(x)
    x = Activation('tanh')(x)
    #x = Bias()(x)
    x = Add()([x,rec_exp])
    output = Add()([x,rec_id])

    gcn_comp = Model([rec_id, rec_exp], output) 
    #gcn_comp = multi_gpu_model(Model([rec_id, rec_exp], output), gpus=2)

    if vis:
        encoder.summary()
        decoder_id.summary()
        decoder_exp.summary()
        gcn_comp.summary()
    #------------------------------
    # Build VAE loss
    #------------------------------
    new_rec_id = decoder_id(encoder(inputs)[-2])
    new_rec_exp = decoder_exp(encoder(inputs)[-1])
    reconstruction_loss = inputs-gcn_comp([new_rec_id, new_rec_exp])

    
    kl_loss_id = 1 + z_log_var_id - K.square(z_mean_id) - K.exp(z_log_var_id)
    kl_loss_id = K.mean(K.abs(K.sum(kl_loss_id, axis=-1)))
    
    kl_loss_exp = 1 + z_log_var_exp - K.square(z_mean_exp) - K.exp(z_log_var_exp)
    kl_loss_exp = K.mean(K.abs(K.sum(kl_loss_exp, axis=-1)))
    return gcn_comp, encoder, encoder_id, encoder_exp, decoder_id, decoder_exp, z_id, z_exp, reconstruction_loss, kl_loss_id, kl_loss_exp

def get_gcn(T_k, support = 3, batch_size = 1, v = 11510, feature_dim = 9, input_dim = 11510 * 9, vis = False):
    g = [K.variable(_) for _ in T_k]
    def gcn(x):
        supports = list()
        for i in range(support):
            num , v , feature_shape = K.int_shape(x)
            LF = list()
            for j in range(batch_size):
                LF.append(K.expand_dims(K.dot(g[i], K.squeeze(K.slice(x, [j,0,0],[1,v,feature_shape]), axis = 0)), axis=0))
            supports.append(K.concatenate(LF,axis=0)) 
        x = K.concatenate(supports)
        return x
    def GConv(x, input_dim, output_dim, support, active_func = LeakyReLU(alpha=0.1)):
        x = Lambda(gcn, output_shape=(v, support*input_dim))(x)
        x = Dense(output_dim)(x)
        x = Bias()(x)
        x = active_func(x)
        return x
    rec_id = Input(shape=(feature_dim * v, ))
    rec_exp = Input(shape=(feature_dim * v, ))
    x_id = Reshape((v, feature_dim))(rec_id)
    x_exp = Reshape((v, feature_dim))(rec_exp)
    x = Concatenate()([x_id, x_exp])
    # One GCN Layer
    x = GConv(x, 2*feature_dim, 256, support)
    x = GConv(x, 256, 128, support)
    x1 = x
    x = GConv(x, 128, 128, support)
    x = Add()([x,x1])
    x1 = x
    x = GConv(x, 128, 128, support)
    x = Add()([x,x1])
    x1 = x
    x = GConv(x, 128, 128, support)
    x = Add()([x,x1])
    x = GConv(x, 128, 64, support)
    x = GConv(x, 64, feature_dim, support)
    x = Reshape((feature_dim*v,))(x)
    #x = LeakyReLU(alpha=0.1)(x)
    x = Activation('tanh')(x)
#    x = Bias()(x)
    #x = LeakyReLU(alpha=0.1)(x)
    x = Add()([x,rec_exp])
    output = Add()([x,rec_id])
    gcn_comp = Model([rec_id, rec_exp], output)
    if vis:
        gcn_comp.summary()
    
    return gcn_comp

def get_gcn_vae_id(T_k, support = 3, batch_size = 1, v = 11510, feature_dim = 9, input_dim = 11510 * 9, vis = False,hidden_dim = 300, latent_dim = 50):
    g = [K.variable(_) for _ in T_k]
    def gcn(x):
        supports = list()
        for i in range(support):
            num , v , feature_shape = K.int_shape(x)
            LF = list()
            for j in range(batch_size):
                LF.append(K.expand_dims(K.dot(g[i], K.squeeze(K.slice(x, [j,0,0],[1,v,feature_shape]), axis = 0)), axis=0))
            supports.append(K.concatenate(LF,axis=0)) 
        x = K.concatenate(supports)
        return x
    def GConv(x, input_dim, output_dim, support, active_func = LeakyReLU(alpha=0.1)):#Activation('tanh')):#
        x = Lambda(gcn, output_shape=(v, support*input_dim))(x)
        x = Dense(output_dim)(x)
        x = Bias()(x)
        x = active_func(x)
        return x
    inputs = Input(shape=(feature_dim * v, ))
    x = Reshape((v, feature_dim))(inputs)
    # One GCN Layer
    x = GConv(x, feature_dim, 128, support)
    x = GConv(x, 128, 64, support)
    x = GConv(x, 64, 64, support)
    x = GConv(x, 64, 64, support)
    # --------------
    # added
#    y = x
#    y = GConv(y, 64, feature_dim, support)
#    y = Flatten()(y)
    # --------------

    #x = GConv(x, 64, int(feature_dim/3), support, Activation('tanh'))    
    #x = GConv(x, 64, 1, support, Activation('tanh'))
    x = GConv(x, 64, int(feature_dim/3), support)
    # --------------
    # added
#    y = x
#    y = GConv(y, 3, feature_dim, support)
#    y = Flatten()(y)
    # --------------
    x = Flatten()(x)

    
    
    x = Dense(hidden_dim)(x)
    x = LeakyReLU(alpha=0.1)(x)
    z_mean = Dense(latent_dim, name='z_mean')(x)
    x = Activation('sigmoid')(x)
    z_log_var = Dense(latent_dim, name='z_log_var')(x)
    # use reparameterization trick to push the sampling out as input
    # note that "output_shape" isn't necessary with the TensorFlow backend
    z = Lambda(sampling, output_shape=(latent_dim,), name='z')([z_mean, z_log_var])
    
    encoder = Model(inputs,[z_mean, z_log_var, z], name = 'id_encoder')
    code = Input(shape=(latent_dim, ))
    x = Dense(hidden_dim)(code)
    x = LeakyReLU(alpha=0.1)(x)
    x = Dense(v*feature_dim)(x)
    output = Activation('tanh')(x)

    decoder = Model(code, output)
    # --------------
    # added
    #output = Add()([decoder(encoder(inputs)[2]) , y])
    output = decoder(encoder(inputs)[2])
    # --------------

    gcn_vae = Model(inputs, output)
    if vis:
        gcn_vae.summary()
    kl_loss = 1 + z_log_var - K.square(z_mean) - K.exp(z_log_var)
    kl_loss = K.mean(K.abs(K.sum(kl_loss, axis=-1)))
    return kl_loss, encoder, decoder, gcn_vae


def get_gcn_vae_exp(T_k, support = 3, batch_size = 1, v = 11510, feature_dim = 9, input_dim = 11510 * 9, vis = False, hidden_dim = 300,latent_dim = 25):
    g = [K.variable(_) for _ in T_k]
    def gcn(x):
        supports = list()
        for i in range(support):
            num , v , feature_shape = K.int_shape(x)
            LF = list()
            for j in range(batch_size):
                LF.append(K.expand_dims(K.dot(g[i], K.squeeze(K.slice(x, [j,0,0],[1,v,feature_shape]), axis = 0)), axis=0))
            supports.append(K.concatenate(LF,axis=0)) 
        x = K.concatenate(supports)
        return x
    def GConv(x, input_dim, output_dim, support, active_func = LeakyReLU(alpha=0.1)):#Activation('tanh')):#
        x = Lambda(gcn, output_shape=(v, support*input_dim))(x)
        x = Dense(output_dim)(x)
        x = active_func(x)
        return x
    inputs = Input(shape=(feature_dim * v, ))
    x = Reshape((v, feature_dim))(inputs)
    # One GCN Layer
    x = GConv(x, feature_dim, 128, support)
    x = GConv(x, 128, 64, support)
    x = GConv(x, 64, 64, support)
    x = GConv(x, 64, 64, support)
    x = GConv(x, 64, 1, support, Activation('tanh'))
    x = Flatten()(x)

    x = Dense(hidden_dim)(x)
    x = LeakyReLU(alpha=0.1)(x)
    z_mean = Dense(latent_dim, name='z_mean')(x)
    x = Activation('sigmoid')(x)
    z_log_var = Dense(latent_dim, name='z_log_var')(x)
    # use reparameterization trick to push the sampling out as input
    # note that "output_shape" isn't necessary with the TensorFlow backend
    z = Lambda(sampling, output_shape=(latent_dim,), name='z')([z_mean, z_log_var])
    
    encoder = Model(inputs,[z_mean, z_log_var, z], name = 'exp_encoder')
    code = Input(shape=(latent_dim, ))
    x = Dense(hidden_dim)(code)
    x = LeakyReLU(alpha=0.1)(x)
    x = Dense(v*feature_dim)(x)
    output = Activation('tanh')(x)

    decoder = Model(code, output)
    output = decoder(encoder(inputs)[2])
    gcn_vae = Model(inputs, output)
    if vis:
        gcn_vae.summary()
    kl_loss = 1 + z_log_var - K.square(z_mean) - K.exp(z_log_var)
    kl_loss = K.mean(K.abs(K.sum(kl_loss, axis=-1)))
    return kl_loss, encoder, decoder, gcn_vae

if __name__ == '__main__':
    """
    Testing code
    """
    #generate_mesh("Normalized_feature/4.txt", "generate_1.obj")
    start = True
