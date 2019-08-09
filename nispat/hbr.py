#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jul 25 13:23:15 2019

@author: seykia
"""

from __future__ import print_function
from __future__ import division

import numpy as np
import pymc3 as pm
import theano

class HBR:
    """Hierarchical Bayesian Regression for normative modeling

    Basic usage::

        model = HBR(age, site_id, gender, mri_voxel)
        trace = model.estimate()
        ys,s2 = model.predict(age, site_id, gender)

    where the variables are

    :param age: N-vector of ages for N subjects
    :param site_id: N-vector of site IDs for N subjects
    :param gender: N-vector of genders for N subjects
    :param mri_voxel: N-vector of one voxel values for N subjects

    :returns: * ys - predictive mean
              * s2 - predictive variance

    Written by S.M. Kia
    """

    def __init__(self, age, site_id, gender, y, model_type = 'lin'):
        self.site_num = len(np.unique(site_id))
        self.gender_num = len(np.unique(gender))
        self.model_type = model_type
        if model_type == 'nn':
            age = np.expand_dims(age ,axis = 1)
        self.a = theano.shared(age)
        self.s = theano.shared(site_id)
        self.g = theano.shared(gender)
        with pm.Model() as model:
            # Priors
            mu_prior_intercept = pm.Normal('mu_prior_intercept', mu=0., sigma=1e5)
            sigma_prior_intercept = pm.HalfCauchy('sigma_prior_intercept', 5)
            mu_prior_slope = pm.Normal('mu_prior_slope', mu=0., sigma=1e5)
            sigma_prior_slope = pm.HalfCauchy('sigma_prior_slope', 5)
            
            # Random intercepts
            intercepts = pm.Normal('intercepts', mu=mu_prior_intercept, sigma=sigma_prior_intercept, shape=self.site_num)
            
            # Expected value
            if model_type == 'lin_rand_int':
                # Random slopes
                slopes = pm.Normal('slopes', mu=mu_prior_slope, sigma=sigma_prior_slope, shape=(self.gender_num,))
                y_hat = intercepts[self.s] + self.a * slopes[self.g]
                # Model error
                sigma_error = pm.Uniform('sigma_error', lower=0, upper=100)
                sigma_y = sigma_error
            elif model_type == 'lin_rand_int_slp':
                # Random slopes
                slopes = pm.Normal('slopes', mu=mu_prior_slope, sigma=sigma_prior_slope, shape=(self.gender_num,self.site_num))
                y_hat = intercepts[self.s] + self.a * slopes[self.g, self.s]
                # Model error
                sigma_error = pm.Uniform('sigma_error', lower=0, upper=100)
                sigma_y = sigma_error
            elif model_type == 'lin_rand_int_slp_nse':
                # Random slopes
                slopes = pm.Normal('slopes', mu=mu_prior_slope, sigma=sigma_prior_slope, shape=(self.gender_num,self.site_num))
                y_hat = intercepts[self.s] + self.a * slopes[self.g, self.s]
                # Model error
                sigma_error = pm.Uniform('sigma_error', lower=0, upper=100, shape=(self.gender_num,self.site_num))
                sigma_y = sigma_error[self.g, self.s]      
            elif model_type == 'poly2':
                slopes = pm.Normal('slopes', mu=mu_prior_slope, sigma=sigma_prior_slope, shape=(self.gender_num,self.site_num))
                mu_prior_slope_2 = pm.Normal('mu_prior_slope_2', mu=0., sigma=1e5)
                sigma_prior_slope_2 = pm.HalfCauchy('sigma_prior_slope_2', 5)
                slopes_2 = pm.Normal('slopes_2', mu=mu_prior_slope_2, sigma=sigma_prior_slope_2, shape=(self.gender_num,self.site_num))
                y_hat = intercepts[self.s] + self.a * slopes[self.g, self.s] + self.a**2 * slopes_2[self.g, self.s]
                # Model error
                sigma_error = pm.Uniform('sigma_error', lower=0, upper=100, shape=(self.gender_num,self.site_num))
                sigma_y = sigma_error[self.g, self.s]
            elif model_type == 'nn':
                n_hidden = 2
                n_data = 1
                init_1 = pm.floatX(np.random.randn(n_data, n_hidden))
                init_out = pm.floatX(np.random.randn(n_hidden))
                std_init_1 = pm.floatX(np.ones([n_data, n_hidden]))
                std_init_out = pm.floatX(np.ones([n_hidden,]))
                
                weights_in_1_grp = pm.Normal('w_in_1_grp', 0, sd=1., 
                                 shape=(n_data, n_hidden), 
                                 testval=init_1)
                # Group standard-deviation
                weights_in_1_grp_sd = pm.HalfNormal('w_in_1_grp_sd', sd=1., 
                                         shape=(n_data, n_hidden), 
                                         testval=std_init_1)
                # Group mean distribution from hidden layer to output
                weights_1_out_grp = pm.Normal('w_1_out_grp', 0, sd=1., 
                                          shape=(n_hidden,), 
                                          testval=init_out)
                weights_1_out_grp_sd = pm.HalfNormal('w_1_out_grp_sd', sd=1., 
                                          shape=(n_hidden,), 
                                          testval=std_init_out)
                # Separate weights for each different model, just add a 3rd dimension
                # of weights
                weights_in_1_raw = pm.Normal('w_in_1', 
                                             shape=(self.gender_num, self.site_num, n_data, n_hidden))
                # Non-centered specification of hierarchical model
                weights_in_1 = weights_in_1_raw[self.g, self.s,:,:] * weights_in_1_grp_sd + weights_in_1_grp

                weights_1_out_raw = pm.Normal('w_1_out', 
                                              shape=(self.gender_num, self.site_num, n_hidden))
                weights_1_out = weights_1_out_raw[self.g, self.s,:] * weights_1_out_grp_sd + weights_1_out_grp
                # Build neural-network using tanh activation function
                act_1 = pm.math.tanh(theano.tensor.batched_dot(age, weights_in_1))
                y_hat = theano.tensor.batched_dot(act_1, weights_1_out)
                
                sigma_error = pm.Uniform('sigma_error', lower=0, upper=100, shape=(self.gender_num,self.site_num))
                sigma_y = sigma_error[(self.g, self.s)]
                
            else:
                raise ValueError('Unknown method:' + model_type)
            
            
            
            # Data likelihood
            y_like = pm.Normal('y_like', mu=y_hat, sigma=sigma_y, observed=y)
            
        self.model = model

    def estimate(self):
        """ Function to estimate the model """
        with self.model:
            self.trace = pm.sample(1000, tune=1000, chains=2)
        
        return self.trace

    def predict(self, age, site_id, gender):
        """ Function to make predictions from the model """
        #self.a = theano.shared(age)
        #self.s = theano.shared(site_id)
        #self.g = theano.shared(gender)
        samples = 1000
        if self.model_type == 'nn':
            age = np.expand_dims(age ,axis = 1)
        with self.model:
            self.a.set_value(age)
            self.s.set_value(site_id)
            self.g.set_value(gender)
            ppc = pm.sample_posterior_predictive(self.trace, samples=samples, progressbar=True) 
        
        # Predicting on training set
        pred_mean = ppc['y_like'].mean(axis=0)
        pred_var = ppc['y_like'].var(axis=0)
        
        temp = np.zeros([len(age), self.trace.nchains * samples])
        for i in range(temp.shape[0]):
            if (self.model_type == 'lin_rand_int' or self.model_type == 'lin_rand_int_slp' or self.model_type == 'lin_rand_int_slp_nse'):
                temp[i,:] = age[i] * self.trace['mu_prior_slope'] + self.trace['mu_prior_intercept']
            elif self.model_type == 'poly2':
                temp[i,:] = age[i]**2 * self.trace['mu_prior_slope_2'] + age[i] * self.trace['mu_prior_slope'] + self.trace['mu_prior_intercept']
            elif self.model_type == 'nn':
                act_1 = pm.math.tanh(age[i,:] * self.trace['w_in_1_grp'])
                temp[i,:] = theano.tensor.batched_dot(act_1, self.trace['w_1_out_grp'])
                
        group_mean = temp.mean(axis=1)
        group_var = temp.var(axis=1)
        
        print('Done!')
        
        
        return pred_mean, pred_var
