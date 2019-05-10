import sys
import os
import numpy as np
import tensorflow as tf

from data_loader import import_data,random_batcher,import_labels

#os.environ['CUDA_VISIBLE_DEVICES'] = '0'
def train_network(train_index,test_index,txt_loc,lbl_loc,learning_rate,training_steps,batch_size,
    save_interval,num_classes,model_path,drop_features,glom_samplings,drop1,drop2):

    # Training Parameters

    display_step = 50

    # Network Parameters

    num_hidden = 50
    num_hidden_2 = 25


    # Location of data, labels, and desired output loss log file

    loss_txt='loss.txt'

    # Import data and labels
    all_features = np.array(import_data(txt_loc))


    labels=np.array(import_labels(lbl_loc))

    for case in range(0,len(all_features)):
        for glom in range(0,len(all_features[case])):
            for f_ in drop_features[::-1]:

                all_features[case][glom].pop(f_-1)


    # Before doing anything, identify the mean and standard deviation of all features,
    # for standardization purposes
    mean_record=[]
    std_record=[]

    for case in all_features:

        mean_record.append(np.mean(np.asarray(case),0))
        std_record.append(np.std(np.asarray(case),0))
    feature_mean=np.nanmean(mean_record,0)
    feature_std=np.nanstd(std_record,0)
    feature_min=np.nanmin(mean_record,0)
    feature_max=np.nanmax(mean_record,0)


    # Identify cases for training and cases for testing
    train_features=all_features[train_index]
    train_labels=labels[train_index]

    holdout_features=all_features[test_index]
    holdout_labels=labels[test_index]


    # Number of input features for the network
    num_input=len(train_features[0][0])

    # Define placeholders for graph input
    X = tf.placeholder(tf.float32, [None, glom_samplings, num_input])
    Y = tf.placeholder(tf.float32, [None, 1])
    dropout1 = tf.placeholder(tf.float32,shape=(),name='dropout1')
    dropout2 = tf.placeholder(tf.float32,shape=(),name='dropout2')

    # Function to return LSTM during graph definition
    def lstm(x_,unit_num,seq_flag):
        lstm_cell =tf.keras.layers.LSTMCell(unit_num, unit_forget_bias=True)
        lstm_layer= tf.keras.layers.RNN(lstm_cell,return_sequences=seq_flag,unroll=True, dtype=tf.float32)
        output=lstm_layer(x_)
        return output

    # Define a function that returns mean squared error on a batch
    def MSE(x,y):
        return np.sum((x-y)**2)/batch_size

    # Dense layer to select input feature importance
    D_in=tf.layers.dense(X,num_input,activation=tf.nn.leaky_relu)
    # Dropout to reduce overfit
    D_in=tf.nn.dropout(D_in,dropout1)
    # First lstm layer
    cell_1 = lstm(x_=D_in,unit_num=num_hidden,seq_flag=True)
    # Dropout between LSTM cells
    cell_1=tf.nn.dropout(cell_1,dropout2)
    # Second LSTM layer
    cell_2 = lstm(x_=cell_1,unit_num=num_hidden_2,seq_flag=False)
    # Network output
    prediction=tf.layers.dense(cell_2,1,activation=tf.nn.leaky_relu)
    # Clipped prediction value between 1 and max class value
    clipped_prediction=tf.clip_by_value(prediction,1,num_classes)

    # Define loss and optimizer
    loss_op = tf.reduce_mean(abs( prediction - Y) )
    optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
    train_op = optimizer.minimize(loss_op)

    # Performance metric
    MSE_ = tf.reduce_mean(MSE(prediction,Y))

    # Initialize the variables (i.e. assign their default value)
    init = tf.global_variables_initializer()

    # Save model
    saver=tf.train.Saver(max_to_keep=int(round(training_steps/save_interval)))

    #Save holdout indices and labels to text file
    f=open(loss_txt,'w')
    f=open(loss_txt,'a+')
    for h in test_index:
        f.write(str(h))
        f.write(',')
    for h in holdout_labels:
        f.write(str(h))
        f.write(',')
    f.write('\n')
    f.close()

    # Start training
    with tf.Session() as sess:

        # Run the initializer
        sess.run(init)

        #For training steps
        for step in range(1, training_steps+1):

            # Pull a random batch of sequences from the training data
            batch_x,batch_y = random_batcher(train_features,glom_samplings,batch_size,train_labels)
            # Standardize the features before input to network
            batch_x-=feature_mean
            batch_x/=feature_std
            batch_x=np.nan_to_num(batch_x)
            # In case any features have a standard deviation  of zero / near zero which results in NaN during normalization
            #batch_x=np.nan_to_num(batch_x)

            # Pull a random holdout batch of sequences from the holdout patients, for validation
            holdout_batch,holdout_label=random_batcher(holdout_features,glom_samplings,batch_size,holdout_labels)

            # Standardize
            holdout_batch-=feature_mean
            holdout_batch/=feature_std
            holdout_batch=np.nan_to_num(holdout_batch)
            # In case any features have a standard deviation of zero / near zero which results in NaN during normalization
            #holdout_batch=np.nan_to_num(holdout_batch)

            # Run the graph, return the training loss, MSE, and sample predictions
            _,loss, acc,pred = sess.run([train_op,loss_op, MSE_,prediction], feed_dict={X: batch_x,
                                                                 Y: batch_y, dropout1: drop1, dropout2: drop2})


            if step % display_step == 0 or step == 1:
                # Calculate batch loss and MSE
                # Run the graph for validation, return the validation loss, validation MSE, and a clipped prediction
                val_loss,val_acc,c_p = sess.run([loss_op,MSE_,clipped_prediction], feed_dict={X: holdout_batch, Y: holdout_label, dropout1: 1, dropout2: 1})
                # Print some information to the command line
                print("Step " + str(step) + ", Train Loss= " + \
                      "{:.4f}".format(loss) + ", Val loss= " + \
                      "{:.4f}".format(val_loss) + ", Sample prediction= " + \
                      "{:.4f}".format(float(c_p[0]))  + ", Val ME= " + \
                      "{:.4f}".format(np.sqrt(float(val_acc)))

                      )
                # save the losses for future analysis
                with open(loss_txt,'a') as f:
                    f.write(str(step)+':'+str(loss)+':'+str(val_loss)+'\n')
            # save some checkpoints
            if (step+1) % save_interval == 1:
                saved_path=saver.save(sess, model_path + '/' +str(step)+'_model.ckpt')


        return saved_path
        print("Optimization Finished!")
