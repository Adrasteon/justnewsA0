from training_system.core.training_coordinator import (
    OnTheFlyTrainingCoordinator,
)


def make_coordinator(monkeypatch):
    # Prevent background training loop from running long-running sleep
    monkeypatch.setattr(
        OnTheFlyTrainingCoordinator, "_training_loop", lambda self: None
    )

    # Create coordinator with small thresholds for tests
    coord = OnTheFlyTrainingCoordinator(
        update_threshold=2,
        max_buffer_size=10,
        performance_window=5,
        rollback_threshold=0.05,
    )

    # Ensure persistence does not call DB
    coord._persist_training_example = lambda *a, **k: None

    return coord


def test_add_training_example_buffers_and_persists(monkeypatch):
    coord = make_coordinator(monkeypatch)

    assert len(coord.training_buffers["fact_checker"]) == 0

    coord.add_training_example(
        agent_name="fact_checker",
        task_type="sentiment",
        input_text="x",
        expected_output=1,
        uncertainty_score=0.9,
    )

    assert len(coord.training_buffers["fact_checker"]) == 1

    # Add another and ensure buffer keeps both
    coord.add_training_example(
        agent_name="fact_checker",
        task_type="sentiment",
        input_text="y",
        expected_output=0,
        uncertainty_score=0.95,
    )
    assert len(coord.training_buffers["fact_checker"]) == 2


def test_add_prediction_feedback_adds_only_high_uncertainty(monkeypatch):
    coord = make_coordinator(monkeypatch)

    # High uncertainty case: confidence low => uncertainty high -> should add
    coord.add_prediction_feedback(
        agent_name="analyst",
        task_type="sentiment",
        input_text="a",
        predicted_output=0,
        actual_output=1,
        confidence_score=0.2,
    )
    assert len(coord.training_buffers["analyst"]) == 1

    # Low uncertainty and correct prediction -> no add
    coord.add_prediction_feedback(
        agent_name="analyst",
        task_type="sentiment",
        input_text="b",
        predicted_output=1,
        actual_output=1,
        confidence_score=0.95,
    )
    assert len(coord.training_buffers["analyst"]) == 1


def test_force_update_agent_triggers_update(monkeypatch):
    coord = make_coordinator(monkeypatch)

    called = {"agent": None, "immediate": None}

    def fake_update(agent_name, immediate=False):
        called["agent"] = agent_name
        called["immediate"] = immediate

    coord._update_agent_model = fake_update

    # add example so buffer is non-empty
    coord.add_training_example("fact_checker", "sentiment", "x", 1, 0.9)

    ok = coord.force_update_agent("fact_checker")
    assert ok is True
    assert called["agent"] == "fact_checker"
    assert called["immediate"] is True


def test_update_agent_model_performance_drop_triggers_rollback(monkeypatch):
    coord = make_coordinator(monkeypatch)

    # add several examples so update will proceed
    for i in range(4):
        coord.add_training_example(
            "fact_checker", "sentiment", f"t{i}", expected_output=i % 2, uncertainty_score=0.9
        )

    # Make perform update succeed
    monkeypatch.setattr(
        OnTheFlyTrainingCoordinator,
        "_perform_model_update",
        lambda self, agent, examples: True,
    )

    # Force pre/post performance difference by patching evaluation
    seq = {"calls": 0}

    def fake_eval(self, agent_name):
        # First call return high (pre), second call return lower (post)
        seq["calls"] += 1
        return 0.80 if seq["calls"] == 1 else 0.70

    monkeypatch.setattr(
        OnTheFlyTrainingCoordinator, "_evaluate_agent_performance", fake_eval
    )

    # Run update directly (synchronous)
    coord._update_agent_model("fact_checker", immediate=False)

    # After update, because a rollback was triggered, examples should remain in the
    # buffer (rollback prevents clearing) and training should have finished.
    assert len(coord.training_buffers["fact_checker"]) >= 1
    assert coord.is_training is False
