from util import remote_fn


@remote_fn
def scrub(volume_id):
    import rawfile_util
    rawfile_util.scrub(volume_id)


@remote_fn
def init_rawfile(volume_id, size):
    import rawfile_util
    rawfile_util.init_rawfile(volume_id, size)


@remote_fn
def expand_rawfile(volume_id, size):
    import rawfile_util
    rawfile_util.expand_rawfile(volume_id, size)
