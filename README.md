RawFile Shared
===

This is a fork of [RawFilePV](https://github.com/openebs/rawfile-localpv.git).
Please read its README for the general info and motivation.

The fork modifies the functionality of the plugin as follows:
- `data-dir` volume, where filesystem images are stored, assumed to be a filesystem accessible (mountable) on every node. Typically is NFS.
- volumes are created **without** topology constraints, which makes them accessible on every node.
- Controller implements `PUBLISH_UNPUBLISH_VOLUME` capability to ensure `ReadWriteOnce` access mode. It also has the access to `data-dir` volume.

which allows to combine the convenience of having Persistent Volumes backed by filesystems like ext4, xfs or btrfs (borrowed from [RawFilePV](https://github.com/openebs/rawfile-localpv.git)) with the accessibility of those volumes on every node (provided by nfs typically). `direct-io` is enabled for loop devices.

Prerequisite
---
- Kubernetes: 1.19+

Install
---
You must set the chart values to your shared storage like that:

```
sharedStorage:
  nfs:
    server: <some_server>
    path: </some_path>
```
where:
- `<some_server>` is your nfs server
- `<some_path>` is your export path

```
helm install -n kube-system rawfilesh-csi ./deploy/charts/rawfilesh-csi/ -f values.yaml
```


Usage
---

Create a `StorageClass` with your desired options:

```
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: rawfilesh
provisioner: rawfilesh-csi
reclaimPolicy: Delete
allowVolumeExpansion: true
```
