import os
import azure.functions as func
import json
import logging
from datetime import datetime
from azure.identity import DefaultAzureCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (AzureFileVolume,
                                                 Container,
                                                 ContainerGroup,
                                                 ContainerGroupDiagnostics,
                                                 EnvironmentVariable,
                                                 ImageRegistryCredential,
                                                 LogAnalytics,
                                                 ResourceRequests,
                                                 ResourceRequirements,
                                                 Volume,
                                                 VolumeMount)

app = func.FunctionApp()

@app.event_hub_message_trigger(arg_name = "azeventhub",
                               event_hub_name = os.getenv('event_hub_name'),
                               connection = "event_hub_connectionstring") 
def motomap_mapupload(azeventhub: func.EventHubEvent):

    serverpath = os.getenv('storage_serverpath')

    event = azeventhub.get_body().decode('utf-8')

    for record in json.loads(event).get('records'):
        if record.get('operationName') == 'PutRange':
            fileuri = record.get('uri')
            filename = fileuri[fileuri.index(serverpath)+len(serverpath):fileuri.index('?')]
            if filename.endswith('.yml'):
                logging.info('FOUND YAML FILE: ' + filename + ", now creating container...")

                subscription_id = os.getenv('subscription_id')
                container_client = ContainerInstanceManagementClient(DefaultAzureCredential(), subscription_id)

                env_variables = [EnvironmentVariable(name = "MOTOMAP_BASEDIR", value = "/motomap/"), EnvironmentVariable(name = "MOTOMAP_CONFIG", value = "/mapdata/" + filename)]

                imagecredentials= ImageRegistryCredential(server = os.getenv('azurecr'),
                                                          username = os.getenv('azurecr_user'),
                                                          password = os.getenv('azurecr_password') )
                
                file_share = AzureFileVolume(share_name = os.getenv('storage_sharename'),
                                         storage_account_name = os.getenv('storage_account_name'),
                                         storage_account_key = os.getenv('storage_account_key'))

                volume = Volume(name = "mapdata",
                                azure_file = file_share)

                volumemount = VolumeMount(name = "mapdata", mount_path = os.getenv('volume_mount_dir'))

                loganalytics = LogAnalytics(workspace_id = os.getenv('loganalytics_workspace_id'),
                             workspace_key = os.getenv('loganalytics_workspace_key'))

                container = Container(name = "motomap-" + datetime.now().strftime('%Y%m%d-%H%M%S'),
                                      image = os.getenv('azurecr_image'),
                                      resources = ResourceRequirements(requests = ResourceRequests(memory_in_gb = 5, cpu = 1.0)),
                                      volume_mounts = [volumemount],
                                      environment_variables = env_variables)

                container_group = ContainerGroup(location = "Central US",
                                                containers = [container],
                                                os_type = "Linux",
                                                restart_policy = "Never",
                                                volumes = [volume],
                                                diagnostics = ContainerGroupDiagnostics(log_analytics = loganalytics),
                                                image_registry_credentials = [imagecredentials])
                
                # Create the container group
                resource_group_name = "motomap_container"
                container_group_name = "motomap-" + datetime.now().strftime('%Y%m%d-%H%M%S')
                container_client.container_groups.begin_create_or_update(resource_group_name,
                                                                         container_group_name,
                                                                         container_group)
                print("Container Group is created")

            else:
                logging.info('INFO: Non-YAML file uploaded: ' + filename)
