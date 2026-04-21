document.addEventListener('DOMContentLoaded', () => {
    const cards = document.querySelectorAll('.card');
    const startBtn = document.getElementById('start-btn');
    const statusText = document.getElementById('status');
    
    let sequence = [1, 2, 3, 4, 5];
    let currentStep = 0;
    let isClickable = false;

    function initGame() {
        // Reset state
        currentStep = 0;
        isClickable = false;
        statusText.textContent = "Get ready...";
        startBtn.disabled = true;

        // Shuffle sequence and assign to cards
        const indices = GameCore.createShuffledIndices(5);
        cards.forEach((card, i) => {
            card.classList.remove('flipped', 'correct', 'error');
            const back = card.querySelector('.card-back');
            const value = sequence[indices[i]];
            back.textContent = value;
            card.dataset.value = value;
        });

        // Show sequence
        setTimeout(() => {
            statusText.textContent = "Memorize!";
            cards.forEach(card => card.classList.add('flipped'));
            
            setTimeout(() => {
                cards.forEach(card => card.classList.remove('flipped'));
                statusText.textContent = "Click in order (1 to 5)";
                isClickable = true;
            }, 3000);
        }, 1000);
    }

    cards.forEach(card => {
        card.addEventListener('click', () => {
            if (!isClickable || card.classList.contains('flipped')) return;

            const clickedValue = parseInt(card.dataset.value);
            card.classList.add('flipped');

            if (GameCore.isExpectedClick(clickedValue, sequence, currentStep)) {
                card.classList.add('correct');
                currentStep++;

                if (currentStep === sequence.length) {
                    statusText.textContent = "Brain Level: MASTER! 🎉";
                    isClickable = false;
                    startBtn.disabled = false;
                    startBtn.textContent = "Play Again";
                } else {
                    statusText.textContent = `Correct! Next: ${sequence[currentStep]}`;
                }
            } else {
                card.classList.add('error');
                statusText.textContent = "Brain Overload! Resetting...";
                isClickable = false;
                
                setTimeout(() => {
                    initGame();
                }, 1500);
            }
        });
    });

    startBtn.addEventListener('click', initGame);
});
