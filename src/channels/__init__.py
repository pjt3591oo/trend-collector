"""Config-selected output adapters, independent of collection sources."""
from src.channels.base import Channel, Post
from src.channels.threads import ThreadsChannel


def build_channels(settings, factories=None):
    factories = factories if factories is not None else {'threads': ThreadsChannel}
    channels = {}
    for name, config in settings.items():
        if config.get('enabled', False):
            if name not in factories:
                raise ValueError(f'Unknown channel: {name}')
            channels[name] = factories[name](config)
    return channels
