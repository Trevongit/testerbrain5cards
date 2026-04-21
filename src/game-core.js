(function (globalScope) {
    'use strict';

    function createShuffledIndices(count, rng) {
        const random = typeof rng === 'function' ? rng : Math.random;
        const indices = Array.from({ length: count }, (_, index) => index);

        for (let i = indices.length - 1; i > 0; i--) {
            const j = Math.floor(random() * (i + 1));
            [indices[i], indices[j]] = [indices[j], indices[i]];
        }

        return indices;
    }

    function isExpectedClick(clickedValue, sequence, currentStep) {
        return Number(clickedValue) === sequence[currentStep];
    }

    const gameCore = {
        createShuffledIndices,
        isExpectedClick,
    };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = gameCore;
    }

    globalScope.GameCore = gameCore;
})(typeof window !== 'undefined' ? window : globalThis);
