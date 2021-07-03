from pathlib import Path

import grpc
from google.protobuf.wrappers_pb2 import BoolValue

import rawfile_util
from consts import PROVISIONER_VERSION, PROVISIONER_NAME
from csi import csi_pb2, csi_pb2_grpc
from declarative import be_symlink, be_absent
from metrics import device_stats, mountpoint_to_dev
from rawfile_util import attach_loop, detach_loops
from rawfile_util import init_rawfile, scrub, expand_rawfile
from util import log_grpc_request, run

NODE_NAME_TOPOLOGY_KEY = "kubernetes.io/hostname"


class RawFileIdentityServicer(csi_pb2_grpc.IdentityServicer):
    def GetPluginInfo(self, request, context):
        return csi_pb2.GetPluginInfoResponse(
            name=PROVISIONER_NAME, vendor_version=PROVISIONER_VERSION
        )

    def GetPluginCapabilities(self, request, context):
        Cap = csi_pb2.PluginCapability
        return csi_pb2.GetPluginCapabilitiesResponse(
            capabilities=[
                Cap(service=Cap.Service(type=Cap.Service.CONTROLLER_SERVICE)),
                Cap(
                    volume_expansion=Cap.VolumeExpansion(
                        type=Cap.VolumeExpansion.ONLINE
                    )
                ),
            ]
        )

    # @log_grpc_request
    def Probe(self, request, context):
        return csi_pb2.ProbeResponse(ready=BoolValue(value=True))


class RawFileNodeServicer(csi_pb2_grpc.NodeServicer):
    def __init__(self, node_name):
        self.node_name = node_name

    # @log_grpc_request
    def NodeGetCapabilities(self, request, context):
        Cap = csi_pb2.NodeServiceCapability
        return csi_pb2.NodeGetCapabilitiesResponse(
            capabilities=[
                Cap(rpc=Cap.RPC(type=Cap.RPC.STAGE_UNSTAGE_VOLUME)),
                Cap(rpc=Cap.RPC(type=Cap.RPC.GET_VOLUME_STATS)),
                Cap(rpc=Cap.RPC(type=Cap.RPC.EXPAND_VOLUME)),
            ]
        )

    def NodePublishVolume(self, request, context):
        target_path = request.target_path
        staging_path = request.staging_target_path
        staging_dev_path = Path(f"{staging_path}/dev")
        be_symlink(path=target_path, to=staging_dev_path)
        return csi_pb2.NodePublishVolumeResponse()

    def NodeUnpublishVolume(self, request, context):
        target_path = request.target_path
        be_absent(path=target_path)
        return csi_pb2.NodeUnpublishVolumeResponse()

    def NodeGetInfo(self, request, context):
        return csi_pb2.NodeGetInfoResponse(
            node_id=self.node_name,
        )

    def NodeStageVolume(self, request, context):
        img_file = rawfile_util.img_file(request.volume_id)
        loop_file = attach_loop(img_file)
        staging_path = request.staging_target_path
        staging_dev_path = Path(f"{staging_path}/dev")
        be_symlink(path=staging_dev_path, to=loop_file)
        return csi_pb2.NodeStageVolumeResponse()

    def NodeUnstageVolume(self, request, context):
        img_file = rawfile_util.img_file(request.volume_id)
        staging_path = request.staging_target_path
        staging_dev_path = Path(f"{staging_path}/dev")
        be_absent(staging_dev_path)
        detach_loops(img_file)
        return csi_pb2.NodeUnstageVolumeResponse()

    # @log_grpc_request
    def NodeGetVolumeStats(self, request, context):
        volume_path = request.volume_path
        dev = mountpoint_to_dev(volume_path)
        stats = device_stats(dev=dev)
        return csi_pb2.NodeGetVolumeStatsResponse(
            usage=[
                csi_pb2.VolumeUsage(
                    total=stats["dev_size"], unit=csi_pb2.VolumeUsage.Unit.BYTES,
                ),
            ]
        )

    def NodeExpandVolume(self, request, context):
        volume_path = request.volume_path
        size = request.capacity_range.required_bytes
        volume_path = Path(volume_path).resolve()
        run(f"losetup -c {volume_path}")
        return csi_pb2.NodeExpandVolumeResponse(capacity_bytes=size)


class RawFileControllerServicer(csi_pb2_grpc.ControllerServicer):
    def ControllerGetCapabilities(self, request, context):
        Cap = csi_pb2.ControllerServiceCapability
        return csi_pb2.ControllerGetCapabilitiesResponse(
            capabilities=[
                Cap(rpc=Cap.RPC(type=Cap.RPC.CREATE_DELETE_VOLUME)),
                Cap(rpc=Cap.RPC(type=Cap.RPC.EXPAND_VOLUME)),
                Cap(rpc=Cap.RPC(type=Cap.RPC.PUBLISH_UNPUBLISH_VOLUME)),
            ]
        )

    def CreateVolume(self, request, context):
        # TODO: volume_capabilities

        if len(request.volume_capabilities) != 1:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT, "Exactly one cap is supported"
            )

        volume_capability = request.volume_capabilities[0]

        AccessModeEnum = csi_pb2.VolumeCapability.AccessMode.Mode
        if volume_capability.access_mode.mode not in [
            AccessModeEnum.SINGLE_NODE_WRITER
        ]:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Unsupported access mode: {AccessModeEnum.Name(volume_capability.access_mode.mode)}",
            )

        # FIXME: re-enable access_type after bd2fs is fixed
        # access_type = volume_capability.WhichOneof("access_type")
        # if access_type == "block":
        #     pass
        # else:
        #     context.abort(
        #         grpc.StatusCode.INVALID_ARGUMENT,
        #         "PANIC! This should be handled by bd2fs!",
        #     )

        MIN_SIZE = 16 * 1024 * 1024  # 16MiB: can't format xfs with smaller volumes
        size = max(MIN_SIZE, request.capacity_range.required_bytes)

        init_rawfile(volume_id=request.name, size=size)

        return csi_pb2.CreateVolumeResponse(
            volume=csi_pb2.Volume(
                volume_id=request.name,
                capacity_bytes=size,
            )
        )

    def DeleteVolume(self, request, context):
        scrub(volume_id=request.volume_id)

        return csi_pb2.DeleteVolumeResponse()

    def ControllerExpandVolume(self, request, context):
        volume_id = request.volume_id
        size = request.capacity_range.required_bytes
        expand_rawfile(volume_id=volume_id, size=size)

        return csi_pb2.ControllerExpandVolumeResponse(
            capacity_bytes=size, node_expansion_required=True,
        )

    # Controller pub/upub

    def ControllerPublishVolume(self, request, context):
        volume_id = request.volume_id
        node_id = request.node_id
        published_at = rawfile_util.metadata(volume_id).get("published_at", "")
        if published_at == node_id:
            # already published at the node
            return csi_pb2.ControllerPublishVolumeResponse()
        if published_at == "":
            rawfile_util.patch_metadata(volume_id, {"published_at": node_id})
            return csi_pb2.ControllerPublishVolumeResponse()

        # already published at another node
        context.abort(
            grpc.StatusCode.FAILED_PRECONDITION,
            f"Already published at node: {node_id}",
        )


    def ControllerUnpublishVolume(self, request, context):
        volume_id = request.volume_id
        rawfile_util.patch_metadata(volume_id, {"published_at": ""})
        return csi_pb2.ControllerUnpublishVolumeResponse()
