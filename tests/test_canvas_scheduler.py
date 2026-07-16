from hoi4cm.ui.canvas_scheduler import DirtyRedrawState, RedrawChannel


def test_requests_coalesce_without_rescheduling_pending_frame():
    state = DirtyRedrawState()

    assert state.request(RedrawChannel.VIEW, "wheel") is True
    assert state.request(RedrawChannel.VIEW, "wheel") is False
    assert state.request(RedrawChannel.SCENE, "model") is False

    request = state.consume()
    assert request.channels == RedrawChannel.VIEW | RedrawChannel.SCENE
    assert request.reasons == {"wheel", "model"}
    assert state.pending is False


def test_focus_list_channel_is_explicit():
    state = DirtyRedrawState()
    state.request(RedrawChannel.VIEW, "pan")

    assert not state.consume().channels & RedrawChannel.FOCUS_LIST
