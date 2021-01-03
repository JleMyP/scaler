import logging
import sys
from datetime import datetime, timedelta
from math import ceil
from typing import Optional, List

import docker
from pydantic import BaseModel, ValidationError


"""
TODO:
ловить какой-нить сигнал и перечитывать сервисы

чистка нод
 вынести в отдельный сервис
 настройки:
  частота запуска
  период неактивности ноды
  фильтры нод
"""


client = docker.from_env()
logger = logging.getLogger(__name__)

services_config = {}


class ServiceConfig(BaseModel):
    enabled: bool
    per_node: int
    node_filter: Optional[dict]
    raw_node_filter: Optional[str]

    @classmethod
    def from_labels(cls, labels: dict) -> 'ServiceConfig':
        return cls(
            enabled=labels.get('scaler.enabled'),
            per_node=labels.get('scaler.per_node'),
            raw_node_filter=labels.get('scaler.node_filter'),
        )


def main():
    refresh_services()

    for event in client.events(filters={'type': 'node', 'event': 'update'}, decode=True):
        e_type, e_action, e_actor = event['Type'], event['Action'], event['Actor']
        if e_type == 'node' and e_action == 'update':
            new_state = e_actor['Attributes'].get('state.new')
            if new_state in ('ready', 'down'):
                logger.info("received state event")
                rescale_all_services()
        elif e_type == 'service':
            service_id, service_name = e_actor['ID'], e_actor['Attributes']['Name']

            if e_action == 'remove':
                if service_id in services_config:
                    del services_config[service_id]
                continue

            service = client.services.get(service_id)
            labels = service.attrs['Spec']['Labels']
            has_config = any([label for label in labels if label.startswith('scaler.')])
            if not has_config:
                if service_id in services_config:
                    del services_config[service_id]
                continue

            try:
                config = ServiceConfig.from_labels(labels)
            except ValidationError as e:
                logger.warning("service %s has incorrect configuration: %s", service_name, e.json())
                continue

            services_config[service_id] = config
            if config.enabled:
                rescale_service(service, config)


def refresh_services(clear: bool = False):
    if clear:
        services_config.clear()

    for service in client.services.list():
        # TODO: дубль
        labels = service.attrs['Spec']['Labels']
        has_config = any([label for label in labels if label.startswith('scaler.')])
        if not has_config:
            continue

        try:
            config = ServiceConfig.from_labels(labels)
        except ValidationError as e:
            logger.warning("service %s has incorrect configuration: %s", service.name, e.json())
            continue

        services_config[service.id] = config


def clean_outdated_nodes():
    for node in client.nodes.list():
        state = node.attrs['Status']['State']
        updated = datetime.fromisoformat(node.attrs['UpdatedAt'][:-4])
        delta = datetime() - updated
        if state == 'down' and delta > timedelta(days=1):
            node.remove()


def rescale_all_services():
    for service_id, config in services_config.items():
        # TODO: catch not found
        service = client.services.get(service_id)
        rescale_service(service, config)


def rescale_service(service: str, config: ServiceConfig, active_nodes: int):
    if not config.enabled:
        return

    current_scale = service.attrs['Spec']['Mode']['Replicated']['Replicas']
    expected_scale = ceil(active_nodes * config.per_node)
    if current_scale != expected_scale:
        logger.info("service %s scaled from %s to %s", service, current_scale, expected_scale)
        service.scale(expected_scale)


def get_active_nodes() -> List:
    nodes = []
    for node in client.nodes.list(filters={'role': 'worker'}):
        if node.attrs['Status']['State'] == 'ready':
            nodes.append(node)
    return nodes


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'clean':
        clean_outdated_nodes()
    else:
        main()
