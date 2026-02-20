"""WebSocket real-time notifications using Socket.IO."""

import socketio
import logging
from typing import Dict, Set

logger = logging.getLogger(__name__)

# Create Socket.IO async server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',  # ← Allow all origins (or specify your frontend URL)
    logger=True,
    engineio_logger=True
)

# Socket.IO ASGI app
socket_app = socketio.ASGIApp(
    sio,
    socketio_path='/socket.io'
)

# Track active connections by tenant
active_connections: Dict[str, Set[str]] = {}


def get_socket_app():
    """Get the Socket.IO ASGI app for mounting."""
    return socket_app


# Socket.IO Event Handlers

@sio.event
async def connect(sid, environ):
    """Handle client connection."""
    logger.info(f"Client connected: {sid}")
    await sio.emit('connected', {
        'message': 'Connected to Lead Gen Platform',
        'sid': sid
    }, room=sid)


@sio.event
async def disconnect(sid):
    """Handle client disconnection."""
    logger.info(f"Client disconnected: {sid}")
    
    # Remove from all tenant rooms
    for tenant_id, sids in list(active_connections.items()):
        if sid in sids:
            sids.remove(sid)
            if not sids:
                del active_connections[tenant_id]


@sio.event
async def join_tenant(sid, data):
    """Join a tenant room for receiving tenant-specific notifications."""
    tenant_id = data.get('tenant_id')
    
    if not tenant_id:
        await sio.emit('error', {
            'message': 'tenant_id is required'
        }, room=sid)
        return
    
    # Add to tenant room
    await sio.enter_room(sid, f'tenant_{tenant_id}')
    
    # Track connection
    if tenant_id not in active_connections:
        active_connections[tenant_id] = set()
    active_connections[tenant_id].add(sid)
    
    logger.info(f"Client {sid} joined tenant room: {tenant_id}")
    
    await sio.emit('joined_tenant', {
        'tenant_id': tenant_id,
        'message': f'Joined tenant room {tenant_id}'
    }, room=sid)


@sio.event
async def ping(sid, data):
    """Handle ping for keepalive."""
    await sio.emit('pong', {
        'timestamp': data.get('timestamp')
    }, room=sid)


# Notification Helper Functions

async def notify_new_leads(tenant_id: str, count: int, source_name: str = None):
    """Notify tenant about new leads available."""
    message = {
        'type': 'new_leads',
        'count': count,
        'source_name': source_name,
        'message': f'{count} new leads available for review'
    }
    
    await sio.emit('new_leads', message, room=f'tenant_{tenant_id}')
    logger.info(f"Notified tenant {tenant_id}: {count} new leads")


async def notify_lead_reviewed(tenant_id: str, lead_id: str, status: str, reviewed_by: str):
    """Notify tenant about a reviewed lead."""
    message = {
        'type': 'lead_reviewed',
        'lead_id': lead_id,
        'status': status,
        'reviewed_by': reviewed_by
    }
    
    await sio.emit('lead_reviewed', message, room=f'tenant_{tenant_id}')
    logger.info(f"Notified tenant {tenant_id}: lead {lead_id} reviewed")


async def notify_queue_updated(tenant_id: str, queue_size: int):
    """Notify tenant about review queue size change."""
    message = {
        'type': 'queue_updated',
        'queue_size': queue_size
    }
    
    await sio.emit('queue_updated', message, room=f'tenant_{tenant_id}')


async def notify_batch_complete(tenant_id: str, batch_id: str, processed: int, status: str):
    """Notify tenant about completed batch processing."""
    message = {
        'type': 'batch_complete',
        'batch_id': batch_id,
        'processed': processed,
        'status': status
    }
    
    await sio.emit('batch_complete', message, room=f'tenant_{tenant_id}')
    logger.info(f"Notified tenant {tenant_id}: batch {batch_id} complete")


async def notify_export_complete(tenant_id: str, export_id: str, lead_count: int, destination: str):
    """Notify tenant about completed export."""
    message = {
        'type': 'export_complete',
        'export_id': export_id,
        'lead_count': lead_count,
        'destination': destination
    }
    
    await sio.emit('export_complete', message, room=f'tenant_{tenant_id}')
    logger.info(f"Notified tenant {tenant_id}: export {export_id} complete")


def get_connection_stats():
    """Get statistics about active connections."""
    return {
        'total_connections': sum(len(sids) for sids in active_connections.values()),
        'tenants_connected': len(active_connections),
        'connections_by_tenant': {
            tenant_id: len(sids)
            for tenant_id, sids in active_connections.items()
        }
    }