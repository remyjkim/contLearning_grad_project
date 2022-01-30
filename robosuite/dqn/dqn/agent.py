from __future__ import print_function
from functools import reduce
import os
import time
import random
import numpy as np
from tqdm import tqdm
import tensorflow as tf

from .base import BaseModel
# from .history import History
from .replay_memory import ReplayMemory
from .ops import linear, conv2d, clipped_error
from .utils import get_time, save_pkl, load_pkl

class Agent(BaseModel):
  def __init__(self, config, environment, task, sess, cutout=False, rgbd=False):
    super(Agent, self).__init__(config, task)
    self.sess = sess
    self.weight_dir = 'weights'

    self.env = environment
    # self.history = History(self.config)
    self.memory = ReplayMemory(self.config, self.model_dir, using_feature=self.env.using_feature)
    self.feature_dim = 9
    self.cutout = cutout
    if not rgbd:
      self.screen_channel = 3

    with tf.variable_scope('step'):
      self.step_op = tf.Variable(0, trainable=False, name='step')
      self.step_input = tf.placeholder('int32', None, name='step_input')
      self.step_assign_op = self.step_op.assign(self.step_input)

    self.build_dqn()

  def train(self):
    start_step = self.step_op.eval()
    start_time = time.time()

    num_game, self.update_count, ep_reward = 0, 0, 0.
    total_reward, self.total_loss, self.total_q = 0., 0., 0.
    max_avg_ep_reward = 0
    ep_rewards, actions = [], []

    screen = self.env.reset()
    count_ep_steps = 0

    # screen, reward, action, terminal = self.env.new_random_game()

    # for _ in range(self.history_length):
    #   self.history.add(screen)

    for self.step in tqdm(range(start_step, self.max_step), ncols=70, initial=start_step):
      if self.step == self.learn_start:
        num_game, self.update_count, ep_reward = 0, 0, 0.
        total_reward, self.total_loss, self.total_q = 0., 0., 0.
        ep_rewards, actions = [], []

      # 1. predict
      action = self.predict(screen)
      # 2. act
      screen, reward, terminal, _ = self.env.step(action)
      print('reward: ', reward)
      screen = np.array(screen)
      # screen, reward, terminal = self.env.act(action, is_training=True)
      # 3. observe
      self.observe(screen, reward, action, terminal)

      if terminal:
        ep_reward += reward
        print('Episode done. - ep len:', count_ep_steps, '   ep reward:', ep_reward)
        screen = self.env.reset()
        count_ep_steps = 0
        # screen, reward, action, terminal = self.env.new_random_game()

        num_game += 1
        ep_rewards.append(ep_reward)
        ep_reward = 0.
      else:
        ep_reward += reward

      actions.append(action)
      total_reward += reward

      if self.step >= self.learn_start:
        if self.step % self.test_step == self.test_step - 1:
          avg_reward = total_reward / self.test_step
          avg_loss = self.total_loss / self.update_count
          avg_q = self.total_q / self.update_count

          try:
            max_ep_reward = np.max(ep_rewards)
            min_ep_reward = np.min(ep_rewards)
            avg_ep_reward = np.mean(ep_rewards)
          except:
            max_ep_reward, min_ep_reward, avg_ep_reward = 0, 0, 0

          print('\navg_r: %.4f, avg_l: %.6f, avg_q: %3.6f, avg_ep_r: %.4f, max_ep_r: %.4f, min_ep_r: %.4f, # game: %d' \
              % (avg_reward, avg_loss, avg_q, avg_ep_reward, max_ep_reward, min_ep_reward, num_game))

          if max_avg_ep_reward * 0.9 <= avg_ep_reward:
            self.step_assign_op.eval({self.step_input: self.step + 1})
            self.save_model(self.step + 1)

            max_avg_ep_reward = max(max_avg_ep_reward, avg_ep_reward)

          if self.step > 180:
            self.inject_summary({
                'average.reward': avg_reward,
                'average.loss': avg_loss,
                'average.q': avg_q,
                'episode.max reward': max_ep_reward,
                'episode.min reward': min_ep_reward,
                'episode.avg reward': avg_ep_reward,
                'episode.num of game': num_game,
                'episode.rewards': ep_rewards,
                'episode.actions': actions,
                'training.learning_rate': self.learning_rate_op.eval({self.learning_rate_step: self.step}),
              }, self.step)

          num_game = 0
          total_reward = 0.
          self.total_loss = 0.
          self.total_q = 0.
          self.update_count = 0
          ep_reward = 0.
          ep_rewards = []
          actions = []

  def demo_keyboard(self):
    start_step = self.step_op.eval()
    start_time = time.time()

    num_game, self.update_count, ep_reward = 0, 0, 0.
    total_reward, self.total_loss, self.total_q = 0., 0., 0.
    max_avg_ep_reward = 0
    ep_rewards, actions = [], []

    screen = self.env.reset()
    count_ep_steps = 0

    for self.step in tqdm(range(start_step, self.max_step), ncols=70, initial=start_step):
      if self.step == self.learn_start:
        num_game, self.update_count, ep_reward = 0, 0, 0.
        total_reward, self.total_loss, self.total_q = 0., 0., 0.
        ep_rewards, actions = [], []

      # 1. predict
      action = int(input('\nnext action? '))
      # action = self.predict(screen)
      # 2. act
      screen, reward, terminal, _ = self.env.step(action)
      print('reward: ', reward)
      screen = np.array(screen)
      # screen, reward, terminal = self.env.act(action, is_training=True)
      # 3. observe
      self.observe(screen, reward, action, terminal)

      if terminal:
        ep_reward += reward
        print('Episode done. - ep len:', count_ep_steps, '   ep reward:', ep_reward)
        screen = self.env.reset()
        count_ep_steps = 0
        # screen, reward, action, terminal = self.env.new_random_game()

        num_game += 1
        ep_rewards.append(ep_reward)
        ep_reward = 0.
      else:
        ep_reward += reward

      actions.append(action)
      total_reward += reward

      if self.step >= self.learn_start:
        if self.step % self.test_step == self.test_step - 1:
          avg_reward = total_reward / self.test_step
          avg_loss = self.total_loss / self.update_count
          avg_q = self.total_q / self.update_count

          try:
            max_ep_reward = np.max(ep_rewards)
            min_ep_reward = np.min(ep_rewards)
            avg_ep_reward = np.mean(ep_rewards)
          except:
            max_ep_reward, min_ep_reward, avg_ep_reward = 0, 0, 0

          print('\navg_r: %.4f, avg_l: %.6f, avg_q: %3.6f, avg_ep_r: %.4f, max_ep_r: %.4f, min_ep_r: %.4f, # game: %d' \
              % (avg_reward, avg_loss, avg_q, avg_ep_reward, max_ep_reward, min_ep_reward, num_game))

          if max_avg_ep_reward * 0.9 <= avg_ep_reward:
            self.step_assign_op.eval({self.step_input: self.step + 1})
            self.save_model(self.step + 1)

            max_avg_ep_reward = max(max_avg_ep_reward, avg_ep_reward)

          if self.step > 180:
            self.inject_summary({
                'average.reward': avg_reward,
                'average.loss': avg_loss,
                'average.q': avg_q,
                'episode.max reward': max_ep_reward,
                'episode.min reward': min_ep_reward,
                'episode.avg reward': avg_ep_reward,
                'episode.num of game': num_game,
                'episode.rewards': ep_rewards,
                'episode.actions': actions,
                'training.learning_rate': self.learning_rate_op.eval({self.learning_rate_step: self.step}),
              }, self.step)

          num_game = 0
          total_reward = 0.
          self.total_loss = 0.
          self.total_q = 0.
          self.update_count = 0
          ep_reward = 0.
          ep_rewards = []
          actions = []

  def predict(self, s_t, test_ep=None):
    ep = test_ep or (self.ep_end +
        max(0., (self.ep_start - self.ep_end)
          * (self.ep_end_t - max(0., self.step - self.learn_start)) / self.ep_end_t))

    if random.random() < ep:
      action = random.randrange(self.env.action_size)
    else:
      action = self.q_action.eval({self.s_t: [s_t]})[0]

    return action

  def observe(self, screen, reward, action, terminal):
    reward = max(self.min_reward, min(self.max_reward, reward))

    # self.history.add(screen)
    self.memory.add(screen, reward, action, terminal)

    if self.step > self.learn_start:
      if (self.step+1) % self.train_frequency == 0:
        self.q_learning_mini_batch()

      if self.step % self.target_q_update_step == self.target_q_update_step - 1:
        self.update_target_q_network()

  def random_cutout(self, states, p=0.7, min_cut=5, max_cut=20):
    n, f, h, w, c = states.shape
    imgs = states.reshape([n*f, h, w, c])

    w1 = np.random.randint(min_cut, max_cut, 2 * n)
    h1 = np.random.randint(min_cut, max_cut, 2 * n)
    cw1 = np.random.randint(0, w - max_cut, 2 * n)
    ch1 = np.random.randint(0, h - max_cut, 2 * n)
    cutouts = np.empty((n * f, h, w, c), dtype=imgs.dtype)
    for i, (img, w11, h11, cw11, ch11) in enumerate(zip(imgs, w1, h1, cw1, ch1)):
      cut_img = img.copy()
      if random.random() < p:
        cut_img[ch11:ch11 + h11, cw11:cw11 + w11, :] = 0
      cutouts[i] = cut_img

    cutouts = cutouts.reshape([n, f, h, w, c])
    return cutouts

  def q_learning_mini_batch(self):
    # if self.memory.count < self.history_length:
    #   return
    # else:
    s_t, action, reward, s_t_plus_1, terminal = self.memory.sample()

    ## data augmentation ##
    if self.cutout:
      s_t = self.random_cutout(s_t)
      s_t_plus_1 = self.random_cutout(s_t_plus_1)

    t = time.time()
    if self.double_q:
      # Double Q-learning
      pred_action = self.q_action.eval({self.s_t: s_t_plus_1})

      q_t_plus_1_with_pred_action = self.target_q_with_idx.eval({
        self.target_s_t: s_t_plus_1,
        self.target_q_idx: [[idx, pred_a] for idx, pred_a in enumerate(pred_action)]
      })
      target_q_t = (1. - terminal) * self.discount * q_t_plus_1_with_pred_action + reward
    else:
      q_t_plus_1 = self.target_q.eval({self.target_s_t: s_t_plus_1})

      terminal = np.array(terminal) + 0.
      max_q_t_plus_1 = np.max(q_t_plus_1, axis=1)
      target_q_t = (1. - terminal) * self.discount * max_q_t_plus_1 + reward

    _, q_t, loss, summary_str = self.sess.run([self.optim, self.q, self.loss, self.q_summary], {
      self.target_q_t: target_q_t,
      self.action: action,
      self.s_t: s_t,
      self.learning_rate_step: self.step,
    })

    self.writer.add_summary(summary_str, self.step)
    self.total_loss += loss
    self.total_q += q_t.mean()
    self.update_count += 1

  def build_dqn(self):
    self.w = {}
    self.t_w = {}

    #initializer = tf.contrib.layers.xavier_initializer()
    initializer = tf.truncated_normal_initializer(0, 0.02)
    activation_fn = tf.nn.relu

    # training network
    with tf.variable_scope('prediction'):
      if self.env.using_feature:
        self.s_t = tf.placeholder('float32', [None, self.feature_dim], name='s_t')

        self.l1, self.w['l1_w'], self.w['l1_b'] = linear(self.s_t, 32, activation_fn=activation_fn, name='l1')
        self.l2, self.w['l2_w'], self.w['l2_b'] = linear(self.l1, 32, activation_fn=activation_fn, name='l2')
        self.q, self.w['q_w'], self.w['q_b'] = linear(self.l2, self.env.action_size, name='q')

      else:
        if self.cnn_format == 'NHWC':
          self.s_t = tf.placeholder('float32',
              [None, 2, self.screen_height, self.screen_width, self.screen_channel], name='s_t')
        else:
          self.s_t = tf.placeholder('float32',
              [None, 2, self.screen_channel, self.screen_height, self.screen_width], name='s_t')

        self.s_t_0 = self.s_t[:, 0, :, :]
        self.s_t_1 = self.s_t[:, 1, :, :]

        self.l1_0, self.w['l1_w0'], self.w['l1_b0'] = conv2d(self.s_t_0,
            32, [8, 8], [4, 4], initializer, activation_fn, self.cnn_format, name='l1_0')
        self.l2_0, self.w['l2_w0'], self.w['l2_b0'] = conv2d(self.l1_0,
            64, [4, 4], [2, 2], initializer, activation_fn, self.cnn_format, name='l2_0')
        self.l3_0, self.w['l3_w0'], self.w['l3_b0'] = conv2d(self.l2_0,
            64, [3, 3], [1, 1], initializer, activation_fn, self.cnn_format, name='l3_0')

        self.l1_1, self.w['l1_w1'], self.w['l1_b1'] = conv2d(self.s_t_1,
             32, [8, 8], [4, 4], initializer, activation_fn, self.cnn_format, name='l1_1')
        self.l2_1, self.w['l2_w1'], self.w['l2_b1'] = conv2d(self.l1_1,
             64, [4, 4], [2, 2], initializer, activation_fn, self.cnn_format, name='l2_1')
        self.l3_1, self.w['l3_w1'], self.w['l3_b1'] = conv2d(self.l2_1,
             64, [3, 3], [1, 1], initializer, activation_fn, self.cnn_format, name='l3_1')

        shape = self.l3_0.get_shape().as_list()
        self.l3_flat_0 = tf.reshape(self.l3_0, [-1, reduce(lambda x, y: x * y, shape[1:])])
        self.l3_flat_1 = tf.reshape(self.l3_1, [-1, reduce(lambda x, y: x * y, shape[1:])])
        self.l3_flat = tf.concat([self.l3_flat_0, self.l3_flat_1], axis=1)

        if self.dueling:
          self.value_hid, self.w['l4_val_w'], self.w['l4_val_b'] = \
              linear(self.l3_flat, 512, activation_fn=activation_fn, name='value_hid')

          self.adv_hid, self.w['l4_adv_w'], self.w['l4_adv_b'] = \
              linear(self.l3_flat, 512, activation_fn=activation_fn, name='adv_hid')

          self.value, self.w['val_w_out'], self.w['val_w_b'] = \
            linear(self.value_hid, 1, name='value_out')

          self.advantage, self.w['adv_w_out'], self.w['adv_w_b'] = \
            linear(self.adv_hid, self.env.action_size, name='adv_out')

          # Average Dueling
          self.q = self.value + (self.advantage -
            tf.reduce_mean(self.advantage, reduction_indices=1, keep_dims=True))
        else:
          self.l4, self.w['l4_w'], self.w['l4_b'] = linear(self.l3_flat, 512, activation_fn=activation_fn, name='l4')
          self.q, self.w['q_w'], self.w['q_b'] = linear(self.l4, self.env.action_size, name='q')

      self.q_action = tf.argmax(self.q, dimension=1)

      q_summary = []
      avg_q = tf.reduce_mean(self.q, 0)
      for idx in range(self.env.action_size):
        q_summary.append(tf.summary.histogram('q/%s' % idx, avg_q[idx]))
      self.q_summary = tf.summary.merge(q_summary, 'q_summary')

    # target network
    with tf.variable_scope('target'):
      if self.env.using_feature:
        self.target_s_t = tf.placeholder('float32', [None, self.feature_dim], name='target_s_t')

        self.target_l1, self.t_w['l1_w'], self.t_w['l1_b'] = linear(self.target_s_t, 32, activation_fn=activation_fn, name='target_l1')
        self.target_l2, self.t_w['l2_w'], self.t_w['l2_b'] = linear(self.target_l1, 32, activation_fn=activation_fn, name='target_l2')
        self.target_q, self.t_w['q_w'], self.t_w['q_b'] = linear(self.target_l2, self.env.action_size, name='target_q')

      else:
        if self.cnn_format == 'NHWC':
          self.target_s_t = tf.placeholder('float32',
              [None, 2, self.screen_height, self.screen_width, self.screen_channel], name='target_s_t')
        else:
          self.target_s_t = tf.placeholder('float32',
              [None, 2, self.screen_channel, self.screen_height, self.screen_width], name='target_s_t')

        self.target_s_t_0 = self.target_s_t[:, 0, :, :]
        self.target_s_t_1 = self.target_s_t[:, 1, :, :]

        self.target_l1_0, self.t_w['l1_w0'], self.t_w['l1_b0'] = conv2d(self.target_s_t_0,
             32, [8, 8], [4, 4], initializer, activation_fn, self.cnn_format, name='target_l1_0')
        self.target_l2_0, self.t_w['l2_w0'], self.t_w['l2_b0'] = conv2d(self.target_l1_0,
             64, [4, 4], [2, 2], initializer, activation_fn, self.cnn_format, name='target_l2_0')
        self.target_l3_0, self.t_w['l3_w0'], self.t_w['l3_b0'] = conv2d(self.target_l2_0,
             64, [3, 3], [1, 1], initializer, activation_fn, self.cnn_format, name='target_l3_0')

        self.target_l1_1, self.t_w['l1_w1'], self.t_w['l1_b1'] = conv2d(self.target_s_t_1,
             32, [8, 8], [4, 4], initializer, activation_fn, self.cnn_format, name='target_l1_1')
        self.target_l2_1, self.t_w['l2_w1'], self.t_w['l2_b1'] = conv2d(self.target_l1_1,
             64, [4, 4], [2, 2], initializer, activation_fn, self.cnn_format, name='target_l2_1')
        self.target_l3_1, self.t_w['l3_w1'], self.t_w['l3_b1'] = conv2d(self.target_l2_1,
             64, [3, 3], [1, 1], initializer, activation_fn, self.cnn_format, name='target_l3_1')

        shape = self.target_l3_0.get_shape().as_list()
        self.target_l3_flat_0 = tf.reshape(self.target_l3_0, [-1, reduce(lambda x, y: x * y, shape[1:])])
        self.target_l3_flat_1 = tf.reshape(self.target_l3_1, [-1, reduce(lambda x, y: x * y, shape[1:])])
        self.target_l3_flat = tf.concat([self.target_l3_flat_0, self.target_l3_flat_1], axis=1)

        '''
        self.target_l1, self.t_w['l1_w'], self.t_w['l1_b'] = conv2d(self.target_s_t, 
            32, [8, 8], [4, 4], initializer, activation_fn, self.cnn_format, name='target_l1')
        self.target_l2, self.t_w['l2_w'], self.t_w['l2_b'] = conv2d(self.target_l1,
            64, [4, 4], [2, 2], initializer, activation_fn, self.cnn_format, name='target_l2')
        self.target_l3, self.t_w['l3_w'], self.t_w['l3_b'] = conv2d(self.target_l2,
            64, [3, 3], [1, 1], initializer, activation_fn, self.cnn_format, name='target_l3')
  
        shape = self.target_l3.get_shape().as_list()
        self.target_l3_flat = tf.reshape(self.target_l3, [-1, reduce(lambda x, y: x * y, shape[1:])])
        '''
        if self.dueling:
          self.t_value_hid, self.t_w['l4_val_w'], self.t_w['l4_val_b'] = \
              linear(self.target_l3_flat, 512, activation_fn=activation_fn, name='target_value_hid')

          self.t_adv_hid, self.t_w['l4_adv_w'], self.t_w['l4_adv_b'] = \
              linear(self.target_l3_flat, 512, activation_fn=activation_fn, name='target_adv_hid')

          self.t_value, self.t_w['val_w_out'], self.t_w['val_w_b'] = \
            linear(self.t_value_hid, 1, name='target_value_out')

          self.t_advantage, self.t_w['adv_w_out'], self.t_w['adv_w_b'] = \
            linear(self.t_adv_hid, self.env.action_size, name='target_adv_out')

          # Average Dueling
          self.target_q = self.t_value + (self.t_advantage -
            tf.reduce_mean(self.t_advantage, reduction_indices=1, keep_dims=True))
        else:
          self.target_l4, self.t_w['l4_w'], self.t_w['l4_b'] = \
              linear(self.target_l3_flat, 512, activation_fn=activation_fn, name='target_l4')
          self.target_q, self.t_w['q_w'], self.t_w['q_b'] = \
              linear(self.target_l4, self.env.action_size, name='target_q')

      self.target_q_idx = tf.placeholder('int32', [None, None], 'outputs_idx')
      self.target_q_with_idx = tf.gather_nd(self.target_q, self.target_q_idx)

    with tf.variable_scope('pred_to_target'):
      self.t_w_input = {}
      self.t_w_assign_op = {}

      for name in self.w.keys():
        self.t_w_input[name] = tf.placeholder('float32', self.t_w[name].get_shape().as_list(), name=name)
        self.t_w_assign_op[name] = self.t_w[name].assign(self.t_w_input[name])

    # optimizer
    with tf.variable_scope('optimizer'):
      self.target_q_t = tf.placeholder('float32', [None], name='target_q_t')
      self.action = tf.placeholder('int64', [None], name='action')

      action_one_hot = tf.one_hot(self.action, self.env.action_size, 1.0, 0.0, name='action_one_hot')
      q_acted = tf.reduce_sum(self.q * action_one_hot, reduction_indices=1, name='q_acted')

      self.delta = self.target_q_t - q_acted

      self.global_step = tf.Variable(0, trainable=False)

      self.loss = tf.reduce_mean(clipped_error(self.delta), name='loss')
      self.learning_rate_step = tf.placeholder('int64', None, name='learning_rate_step')
      self.learning_rate_op = tf.maximum(self.learning_rate_minimum,
          tf.train.exponential_decay(
              self.learning_rate,
              self.learning_rate_step,
              self.learning_rate_decay_step,
              self.learning_rate_decay,
              staircase=True))
      self.optim = tf.train.RMSPropOptimizer(
          self.learning_rate_op, momentum=0.95, epsilon=0.01).minimize(self.loss)

    with tf.variable_scope('summary'):
      scalar_summary_tags = ['average.reward', 'average.loss', 'average.q', \
          'episode.max reward', 'episode.min reward', 'episode.avg reward', 'episode.num of game', 'training.learning_rate']

      self.summary_placeholders = {}
      self.summary_ops = {}

      for tag in scalar_summary_tags:
        self.summary_placeholders[tag] = tf.placeholder('float32', None, name=tag.replace(' ', '_'))
        self.summary_ops[tag]  = tf.summary.scalar("%s-%s/%s" % (self.task, self.env_type, tag), self.summary_placeholders[tag])

      histogram_summary_tags = ['episode.rewards', 'episode.actions']

      for tag in histogram_summary_tags:
        self.summary_placeholders[tag] = tf.placeholder('float32', None, name=tag.replace(' ', '_'))
        self.summary_ops[tag]  = tf.summary.histogram(tag, self.summary_placeholders[tag])

      self.writer = tf.summary.FileWriter('./logs/%s' % self.model_dir, self.sess.graph)

    self._saver = tf.train.Saver(list(self.w.values()) + [self.step_op], max_to_keep=30)

    if self.load_model():
      pass
    else:
      tf.initialize_all_variables().run()

    self.update_target_q_network()

  def update_target_q_network(self):
    for name in self.w.keys():
      self.t_w_assign_op[name].eval({self.t_w_input[name]: self.w[name].eval()})

  def save_weight_to_pkl(self):
    if not os.path.exists(self.weight_dir):
      os.makedirs(self.weight_dir)

    for name in self.w.keys():
      save_pkl(self.w[name].eval(), os.path.join(self.weight_dir, "%s.pkl" % name))

  def load_weight_from_pkl(self, cpu_mode=False):
    with tf.variable_scope('load_pred_from_pkl'):
      self.w_input = {}
      self.w_assign_op = {}

      for name in self.w.keys():
        self.w_input[name] = tf.placeholder('float32', self.w[name].get_shape().as_list(), name=name)
        self.w_assign_op[name] = self.w[name].assign(self.w_input[name])

    for name in self.w.keys():
      self.w_assign_op[name].eval({self.w_input[name]: load_pkl(os.path.join(self.weight_dir, "%s.pkl" % name))})

    self.update_target_q_network()

  def inject_summary(self, tag_dict, step):
    summary_str_lists = self.sess.run([self.summary_ops[tag] for tag in tag_dict.keys()], {
      self.summary_placeholders[tag]: value for tag, value in tag_dict.items()
    })
    for summary_str in summary_str_lists:
      self.writer.add_summary(summary_str, self.step)

  def play(self, n_step=10000, n_episode=100, test_ep=None, render=False):
    if test_ep == None:
      test_ep = self.ep_end

    # test_history = History(self.config)

    # if not self.display:
    #   gym_dir = '/tmp/%s-%s' % (self.env_name, get_time())
    #   self.env.env.monitor.start(gym_dir)

    best_reward, best_idx = -100, 0
    for idx in range(n_episode):
      screen = self.env.reset()
      # screen, reward, action, terminal = self.env.new_random_game()
      current_reward = 0

      # for _ in range(self.history_length):
      #   test_history.add(screen)

      for t in tqdm(range(n_step), ncols=70):
        # 1. predict
        action = self.predict(screen, test_ep)
        # action = self.predict(test_history.get(), test_ep)
        # 2. act
        screen, reward, terminal, _ = self.env.step(action)
        screen = np.array(screen)
        # screen, reward, terminal = self.env.act(action, is_training=False)
        # 3. observe
        # test_history.add(screen)

        current_reward += reward
        if terminal:
          break

      if current_reward > best_reward:
        best_reward = current_reward
        best_idx = idx

      print("="*30)
      print(" [%d] Best reward : %d" % (best_idx, best_reward))
      print("="*30)

    # if not self.display:
    #   self.env.env.monitor.close()
    #   #gym.upload(gym_dir, writeup='https://github.com/devsisters/DQN-tensorflow', api_key='')

class ResNetAgent(Agent):
  def __init__(self, config, environment, task, sess, cutout=False, rgbd=False):
    self.n = 3
    self.beta = 1e-5
    self.is_training = True #is_training
    super(ResNetAgent, self).__init__(config, environment, task, sess, cutout, rgbd)

  def build_dqn(self):
    n = self.n
    initializer = tf.truncated_normal_initializer(0, 0.02)
    activation_fn = tf.nn.relu

    # training network
    with tf.variable_scope('prediction'):
      self.s_t = tf.placeholder('float32', [None, 2, self.screen_height, self.screen_width, self.screen_channel], name='s_t')

      x_0 = self.s_t[:, 0, :, :]
      x_1 = self.s_t[:, 1, :, :]
      h_0 = self.conv_bn_relu(x_0, 16, 'first', stride=1)
      h_1 = self.conv_bn_relu(x_1, 16, 'first', stride=1)

      for i in range(n):
        h_0 = self.res_block(h_0, 16, 'l0-1-' + str(i), i)
        h_1 = self.res_block(h_1, 16, 'l1-1-' + str(i), i)

      for i in range(n):
        h_0 = self.res_block(h_0, 32, 'l0-2-' + str(i), i)
        h_1 = self.res_block(h_1, 32, 'l1-2-' + str(i), i)

      h = tf.concat([h_0, h_1], axis=-1)
      for i in range(n):
        h = self.res_block(h, 64, 'l-3-' + str(i), i)

      h = tf.reshape(h, [-1, self.screen_height * self.screen_width // 64, 64]) #[-1, 8 * 8, 64])
      h = tf.reduce_mean(h, 1)
      # h = tf.reduce_max(h, 1)
      h = self.fc(h, 512, 'fc-1')
      self.q = self.fc(h, self.env.action_size, 'q')

    self.q_action = tf.argmax(self.q, dimension=1)

    q_summary = []
    avg_q = tf.reduce_mean(self.q, 0)
    for idx in range(self.env.action_size):
      q_summary.append(tf.summary.histogram('q/%s' % idx, avg_q[idx]))
    self.q_summary = tf.summary.merge(q_summary, 'q_summary')

    # target network
    with tf.variable_scope('target'):
      self.target_s_t = tf.placeholder('float32', [None, 2, self.screen_height, self.screen_width, self.screen_channel],
                                name='target_s_t')

      x_0 = self.target_s_t[:, 0, :, :]
      x_1 = self.target_s_t[:, 1, :, :]
      h_0 = self.conv_bn_relu(x_0, 16, 'first', stride=1)
      h_1 = self.conv_bn_relu(x_1, 16, 'first', stride=1)

      for i in range(n):
        h_0 = self.res_block(h_0, 16, 'l0-1-' + str(i), i)
        h_1 = self.res_block(h_1, 16, 'l1-1-' + str(i), i)

      for i in range(n):
        h_0 = self.res_block(h_0, 32, 'l0-2-' + str(i), i)
        h_1 = self.res_block(h_1, 32, 'l1-2-' + str(i), i)

      h = tf.concat([h_0, h_1], axis=-1)
      for i in range(n):
        h = self.res_block(h, 64, 'l-3-' + str(i), i)

      h = tf.reshape(h, [-1, self.screen_height * self.screen_width // 64, 64])  # [-1, 8 * 8, 64])
      h = tf.reduce_mean(h, 1)
      # h = tf.reduce_max(h, 1)
      h = self.fc(h, 512, 'fc-1')
      self.target_q = self.fc(h, self.env.action_size, 'q')

    self.target_q_idx = tf.placeholder('int32', [None, None], 'outputs_idx')
    self.target_q_with_idx = tf.gather_nd(self.target_q, self.target_q_idx)

    pred_variables = [w for w in tf.all_variables() if 'prediction' in w.name]
    target_variables = [tw for tw in tf.all_variables() if 'target' in tw.name]
    self.w, self.t_w = {}, {}
    for w in pred_variables:
      w_name = '/'.join(w.name.replace('prediction', '').split('/')[1:]).split(':')[0]
      self.w[w_name] = w
    for tw in target_variables:
      tw_name = '/'.join(tw.name.replace('target', '').split('/')[1:]).split(':')[0]
      self.t_w[tw_name] = tw

    with tf.variable_scope('pred_to_target'):
      self.t_w_input = {}
      self.t_w_assign_op = {}

      for name in self.w.keys():
        self.t_w_input[name] = tf.placeholder('float32', self.t_w[name].get_shape().as_list(), name=name)
        self.t_w_assign_op[name] = self.t_w[name].assign(self.t_w_input[name])

    # optimizer
    with tf.variable_scope('optimizer'):
      self.target_q_t = tf.placeholder('float32', [None], name='target_q_t')
      self.action = tf.placeholder('int64', [None], name='action')

      action_one_hot = tf.one_hot(self.action, self.env.action_size, 1.0, 0.0, name='action_one_hot')
      q_acted = tf.reduce_sum(self.q * action_one_hot, reduction_indices=1, name='q_acted')

      self.delta = self.target_q_t - q_acted

      self.global_step = tf.Variable(0, trainable=False)

      self.loss = tf.reduce_mean(clipped_error(self.delta), name='loss')
      self.learning_rate_step = tf.placeholder('int64', None, name='learning_rate_step')
      self.learning_rate_op = tf.maximum(self.learning_rate_minimum,
                                         tf.train.exponential_decay(
                                           self.learning_rate,
                                           self.learning_rate_step,
                                           self.learning_rate_decay_step,
                                           self.learning_rate_decay,
                                           staircase=True))
      self.optim = tf.train.RMSPropOptimizer(
        self.learning_rate_op, momentum=0.95, epsilon=0.01).minimize(self.loss)

    with tf.variable_scope('summary'):
      scalar_summary_tags = ['average.reward', 'average.loss', 'average.q', \
          'episode.max reward', 'episode.min reward', 'episode.avg reward', 'episode.num of game', 'training.learning_rate']

      self.summary_placeholders = {}
      self.summary_ops = {}

      for tag in scalar_summary_tags:
        self.summary_placeholders[tag] = tf.placeholder('float32', None, name=tag.replace(' ', '_'))
        self.summary_ops[tag]  = tf.summary.scalar("%s-%s/%s" % (self.task, self.env_type, tag), self.summary_placeholders[tag])

      histogram_summary_tags = ['episode.rewards', 'episode.actions']

      for tag in histogram_summary_tags:
        self.summary_placeholders[tag] = tf.placeholder('float32', None, name=tag.replace(' ', '_'))
        self.summary_ops[tag]  = tf.summary.histogram(tag, self.summary_placeholders[tag])

      self.writer = tf.summary.FileWriter('./logs/%s' % self.model_dir, self.sess.graph)

    self._saver = tf.train.Saver(max_to_keep=10)

    if self.load_model():
      pass
    else:
      tf.initialize_all_variables().run()

    self.update_target_q_network()

  ### convolution, maxpooling and fully-connected function ###
  def conv(self, x, num_out, stride, scope):
    with tf.variable_scope(scope, reuse=tf.AUTO_REUSE):
      c_init = tf.contrib.layers.xavier_initializer()
      b_init = tf.constant_initializer(0.0)
      regularizer = tf.contrib.layers.l2_regularizer(scale=self.beta)
      return tf.contrib.layers.conv2d(x, num_out, [3, 3], stride, activation_fn=None,
                                      weights_initializer=c_init, weights_regularizer=regularizer,
                                      biases_initializer=b_init)

  def fc(self, x, num_out, scope):
    with tf.variable_scope(scope, reuse=tf.AUTO_REUSE):
      # f_init = tf.truncated_normal_initializer(stddev=5e-2)
      f_init = tf.contrib.layers.xavier_initializer()
      b_init = tf.constant_initializer(0.0)
      regularizer = tf.contrib.layers.l2_regularizer(scale=self.beta)
      return tf.contrib.layers.fully_connected(x, num_out, activation_fn=None,
                                               weights_initializer=f_init, weights_regularizer=regularizer,
                                               biases_initializer=b_init)

  def batch_norm(self, x, num_out, scope):
    with tf.variable_scope(scope, reuse=tf.AUTO_REUSE):
      beta = tf.Variable(tf.constant(0.0, shape=[num_out]),
                         name='beta', trainable=self.is_training)
      gamma = tf.Variable(tf.constant(1.0, shape=[num_out]),
                          name='gamma', trainable=self.is_training)
      batch_mean, batch_var = tf.nn.moments(x, [0, 1, 2], name='moments')
      ema = tf.train.ExponentialMovingAverage(decay=0.5)

      def mean_var_with_update():
        ema_apply_op = ema.apply([batch_mean, batch_var])
        with tf.control_dependencies([ema_apply_op]):
          return batch_mean, batch_var

      if self.is_training:
        mean, var = mean_var_with_update()
      else:
        mean, var = batch_mean, batch_var

      normed = tf.nn.batch_normalization(x, mean, var, beta, gamma, 1e-5)
    return normed

  def conv_bn_relu(self, x, num_out, scope, stride=1):
    x_conv = self.conv(x, num_out, stride, scope)
    x_bn = self.batch_norm(x_conv, num_out, scope)
    x_relu = tf.nn.relu(x_bn)
    return x_relu

  def shortcut(self, x, num_out, scope):
    with tf.variable_scope(scope, reuse=tf.AUTO_REUSE):
      c_init = tf.contrib.layers.xavier_initializer()
      b_init = tf.constant_initializer(0.0)
      regularizer = tf.contrib.layers.l2_regularizer(scale=self.beta)
      return tf.contrib.layers.conv2d(x, num_out, [1, 1], 2, activation_fn=None,
                                      weights_initializer=c_init, weights_regularizer=regularizer,
                                      biases_initializer=b_init)

  def res_block(self, x, num_out, scope, idx):
    with tf.variable_scope(scope):
      shortcut = x
      # if int(x.shape[3]) != num_out:
      if idx==0:
        shortcut = self.shortcut(x, num_out, scope + '-sc')

      if idx==0:
        x_1 = self.conv_bn_relu(x, num_out, scope + '-1', stride=2)
      else:
        x_1 = self.conv_bn_relu(x, num_out, scope + '-1', stride=1)

      x_2 = self.conv_bn_relu(x_1, num_out, scope + '-2', stride=1)

      return tf.add(x_2, shortcut)
