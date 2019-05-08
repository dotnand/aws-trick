# Automated AMI Backups and Add to AutoScallig group
#
# @author Nand Kishore <nand.kishore@autodesk.com>
#
# This script will search for all instances having a tag with "Aid" or "aid"
# on it. As soon as we have the instances list, we loop through each instance
# and create an AMI of it. Also, it will look for a "Retention" tag key which
# will be used as a retention policy number in days. If there is no tag with
# that name, it will use a 10 days default value for each AMI.
#
# After creating the AMI it creates a "DeleteOn" tag on the AMI indicating when
# it will be deleted using the Retention value and another Lambda function 
# Add the AMI id to the autoscalling group.

import boto3
import collections
import datetime
import sys
import pprint
import time

ec = boto3.client('ec2')

def lambda_handler(event, context):
    
    reservations = ec.describe_instances(
        Filters=[
            {'Name': 'tag-key', 'Values': ['aid', 'Aid']},
        ]
    ).get(
        'Reservations', []
    )

    instances = sum(
        [
            [i for i in r['Instances']]
            for r in reservations
        ], [])

    print "Found %d instances that need backing up" % len(instances)

    to_tag = collections.defaultdict(list)

    for instance in instances:
        try:
            retention_days = [
                int(t.get('Value')) for t in instance['Tags']
                if t['Key'] == 'Retention'][0]
        except IndexError:
            retention_days = 10

            create_time = datetime.datetime.now()
            create_fmt = create_time.strftime('%Y-%m-%d--%H-%M-%S')
        
            AMIid = ec.create_image(InstanceId=instance['InstanceId'], Name="Backups - " + instance['InstanceId'] + " from " + create_fmt, Description="Lambda created AMI of instance " + instance['InstanceId'] + " from " + create_fmt, NoReboot=True, DryRun=False)      
            pprint.pprint(instance)
        
            #to_tag[retention_days].append(AMIid)
            
            to_tag[retention_days].append(AMIid['ImageId'])
            
            print "Retaining AMI %s of instance %s for %d days" % (
                AMIid['ImageId'],
                instance['InstanceId'],
                retention_days,
            ) 
    for retention_days in to_tag.keys():
        delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)
        delete_fmt = delete_date.strftime('%m-%d-%Y')
        print "Will delete %d AMIs on %s" % (len(to_tag[retention_days]), delete_fmt)
        
        #break
    
        ec.create_tags(
            Resources=to_tag[retention_days],
            Tags=[
                {'Key': 'DeleteOn', 'Value': delete_fmt},
            ]
        )
    
	client = boto3.client('autoscaling')
	# get object for the ASG we're going to update, filter by name of target ASG
	response = client.describe_auto_scaling_groups(AutoScalingGroupNames=[event['targetASG']])
	if not response['AutoScalingGroups']:
		return 'No such ASG'
	# get name of InstanceID in current ASG that we'll use to model new Launch Configuration after
	sourceInstanceId = response.get('AutoScalingGroups')[0]['Instances'][0]['InstanceId']
	timeStamp = time.time()
	timeStampString = datetime.datetime.fromtimestamp(timeStamp).strftime('%Y-%m-%d  %H-%M-%S')
	newLaunchConfigName = 'LC '+ AMIid['ImageId'] + ' ' + timeStampString
    client.create_launch_configuration(
        InstanceId = sourceInstanceId,
        LaunchConfigurationName=newLaunchConfigName,
        ImageId= AMIid['ImageId'] )

    # update ASG to use new LC
    response = client.update_auto_scaling_group(AutoScalingGroupName = event['targetASG'],LaunchConfigurationName = newLaunchConfigName)

    print 'Updated ASG `%s` with new launch configuration `%s` which includes AMI `%s`.' % (event['targetASG'], newLaunchConfigName, AMIid['ImageId'])