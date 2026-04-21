import test from 'node:test';
import assert from 'node:assert/strict';
import gameCore from '../src/game-core.js';

function makeRng(values) {
    let idx = 0;
    return () => {
        const value = values[idx] ?? values[values.length - 1] ?? 0;
        idx += 1;
        return value;
    };
}

test('createShuffledIndices returns a full 0..n-1 permutation', () => {
    const result = gameCore.createShuffledIndices(5, makeRng([0.9, 0.7, 0.5, 0.1]));
    const sorted = [...result].sort((a, b) => a - b);

    assert.equal(result.length, 5);
    assert.deepEqual(sorted, [0, 1, 2, 3, 4]);
});

test('createShuffledIndices is deterministic with injected rng', () => {
    const rngValues = [0.9, 0.7, 0.5, 0.1];
    const first = gameCore.createShuffledIndices(5, makeRng(rngValues));
    const second = gameCore.createShuffledIndices(5, makeRng(rngValues));

    assert.deepEqual(first, second);
});

test('isExpectedClick validates the current expected sequence value', () => {
    const sequence = [1, 2, 3, 4, 5];

    assert.equal(gameCore.isExpectedClick(1, sequence, 0), true);
    assert.equal(gameCore.isExpectedClick(2, sequence, 0), false);
    assert.equal(gameCore.isExpectedClick('3', sequence, 2), true);
});
