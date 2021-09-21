RawFile Shared
===

This is a fork of [RawFilePV](https://github.com/openebs/rawfile-localpv.git).
Please read its README for the general info and motivation.

The fork modifies the functionality of the plugin as follows:
- `data-dir` volume, where filesystem images are stored, assumed to be a filesystem accessible (mountable) on every node. Typically is NFS.
- volumes are created **without** topology constraints, which makes them accessible on every node.
- Controller implements `PUBLISH_UNPUBLISH_VOLUME` capability to ensure `ReadWriteOnce` access mode. It also has the access to `data-dir` volume.

which allows to combine the convenience of having Persistent Volumes backed by filesystems like ext4, xfs or btrfs (borrowed from [RawFilePV](https://github.com/openebs/rawfile-localpv.git)) with the accessibility of those volumes on every node (provided by NFS typically). `direct-io` is enabled for loop devices.

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
- `<some_server>` is your NFS server
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

Motivation
----------

One may need to use Kubernetes PersistentVolume:
- with a POSIX compliant filesystem
- not bound to a specific node

in the environment where [iscsi](https://kubernetes.io/docs/concepts/storage/volumes/#iscsi), [rbd](https://kubernetes.io/docs/concepts/storage/volumes/#rbd) or similar are not available and the only available network storage is NFS.

Using NFS as Persistent Volume in k8s is [possible](https://kubernetes.io/docs/concepts/storage/persistent-volumes/#types-of-persistent-volumes). There is no [internal (dynamic) provisioner](https://kubernetes.io/docs/concepts/storage/storage-classes/#provisioner) for NFS in k8s, but there are some [external provisioners](https://kubernetes.io/docs/concepts/storage/storage-classes/#nfs).

Such volume however will have NFS as the filesystem, which depending on the NFS implementation, but genrelally is not seen by some software ([prometheus](https://prometheus.io/docs/prometheus/latest/storage/#operational-aspects), elasticsearch, sqlite3 to name a few) as fully POSIX compliant.

The proposed solution uses NFS to store files, so the data is available across the network, but instead of directly passing mounted NFS to a pod, it takes a file (image of a volume) stored on the mounted NFS, setup a loop device (in direct-io mode) associated with the file and mount the filesystem contained is the file, which is finally passed to a pod as a volume.
