document.addEventListener("DOMContentLoaded", () => {
    /*
     * LedgerFlow interaction layer
     *
     * Principles:
     * - Motion communicates state.
     * - No animation should hide information.
     * - No artificial "live" behavior.
     * - Respect prefers-reduced-motion.
     */

    const reducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)"
    ).matches;


    /*
     * Payment table rows
     *
     * The row itself is navigable, while explicit links/buttons
     * remain independently clickable.
     */
    document.querySelectorAll(
        ".payment-table-row, .table-row-link"
    ).forEach((row) => {
        row.addEventListener("click", (event) => {
            if (
                event.target.closest(
                    "a, button, form, input, select, textarea"
                )
            ) {
                return;
            }

            const href = row.dataset.href;

            if (href) {
                window.location.href = href;
            }
        });

        row.addEventListener("keydown", (event) => {
            if (
                event.key !== "Enter" &&
                event.key !== " "
            ) {
                return;
            }

            if (
                event.target.closest(
                    "a, button, input, select, textarea"
                )
            ) {
                return;
            }

            const href = row.dataset.href;

            if (href) {
                event.preventDefault();
                window.location.href = href;
            }
        });

        if (row.dataset.href) {
            row.setAttribute("tabindex", "0");
            row.setAttribute("role", "link");
        }
    });


    /*
     * Simulator processor behavior selection
     */
    document.querySelectorAll(".behavior-option").forEach((option) => {
        option.addEventListener("click", () => {
            const input = option.querySelector(
                "input[type='radio']"
            );

            if (input) {
                input.checked = true;
            }

            document
                .querySelectorAll(".behavior-option")
                .forEach((item) => {
                    item.classList.remove("is-selected");
                });

            option.classList.add("is-selected");
        });
    });


    /*
     * Metric count animation
     *
     * Only numeric counters using data-count are animated.
     */
    document.querySelectorAll("[data-count]").forEach((element) => {
        const target = Number(element.dataset.count);

        if (!Number.isFinite(target)) {
            return;
        }

        if (reducedMotion || target === 0) {
            element.textContent = target;
            return;
        }

        const duration = 500;
        const start = performance.now();

        const tick = (now) => {
            const progress = Math.min(
                (now - start) / duration,
                1
            );

            const eased =
                1 - Math.pow(1 - progress, 3);

            element.textContent = Math.round(
                target * eased
            );

            if (progress < 1) {
                requestAnimationFrame(tick);
            }
        };

        element.textContent = "0";
        requestAnimationFrame(tick);
    });


    /*
     * Button press feedback
     */
    document.querySelectorAll(
        ".button, .run-button"
    ).forEach((button) => {
        button.addEventListener("pointerdown", () => {
            if (reducedMotion) {
                return;
            }

            button.classList.add("is-pressed");
        });

        const release = () => {
            button.classList.remove("is-pressed");
        };

        button.addEventListener("pointerup", release);
        button.addEventListener("pointercancel", release);
        button.addEventListener("pointerleave", release);
    });


    /*
     * Payment detail hero entrance
     */
    const paymentOrb = document.querySelector(
        ".payment-orb"
    );

    const paymentIdentity = document.querySelector(
        ".payment-identity"
    );

    if (!reducedMotion && paymentOrb) {
        paymentOrb.classList.add("motion-enter");
    }

    if (!reducedMotion && paymentIdentity) {
        paymentIdentity.classList.add(
            "motion-enter-delayed"
        );
    }


    /*
     * Payment lifecycle
     *
     * The HTML determines which steps are active.
     * JavaScript only reveals the existing state progressively.
     */
    const lifecycleSteps =
        document.querySelectorAll(".life-step");

    const lifecycleLines =
        document.querySelectorAll(".life-line.is-active");

    if (reducedMotion) {
        lifecycleSteps.forEach((step) => {
            step.classList.add("is-visible");
        });

        lifecycleLines.forEach((line) => {
            line.classList.add("is-visible");
        });
    } else {
        lifecycleSteps.forEach((step, index) => {
            setTimeout(() => {
                step.classList.add("is-visible");
            }, 120 + index * 90);
        });

        lifecycleLines.forEach((line, index) => {
            setTimeout(() => {
                line.classList.add("is-visible");
            }, 220 + index * 110);
        });
    }


    /*
     * State-aware detail page treatment
     *
     * The template can expose data-payment-state.
     * We do not infer state from visual text.
     */
    const paymentDetail =
        document.querySelector("[data-payment-state]");

    if (paymentDetail) {
        const state =
            paymentDetail.dataset.paymentState;

        paymentDetail.classList.add(
            `payment-state-${String(state).toLowerCase()}`
        );
    }


    /*
     * Processing indicator
     *
     * This is deliberately subtle. It indicates active work
     * without pretending to be a real-time connection.
     */
    document
        .querySelectorAll(".status-processing")
        .forEach((element) => {
            if (!reducedMotion) {
                element.classList.add(
                    "status-motion-enabled"
                );
            }
        });


    /*
     * Overview signal bars
     *
     * These are visual representations of already-calculated
     * server metrics. No values are generated client-side.
     */
    document
        .querySelectorAll("[data-signal-value]")
        .forEach((element) => {
            const value = Number(
                element.dataset.signalValue
            );

            if (
                !Number.isFinite(value) ||
                value < 0
            ) {
                return;
            }

            const bounded = Math.min(value, 100);

            if (reducedMotion) {
                element.style.setProperty(
                    "--signal-progress",
                    `${bounded}%`
                );
                return;
            }

            requestAnimationFrame(() => {
                element.style.setProperty(
                    "--signal-progress",
                    "0%"
                );

                requestAnimationFrame(() => {
                    element.classList.add(
                        "signal-is-ready"
                    );

                    element.style.setProperty(
                        "--signal-progress",
                        `${bounded}%`
                    );
                });
            });
        });


    /*
     * Generic reveal elements
     *
     * Only elements explicitly marked with
     * data-reveal participate.
     */
    const revealElements =
        document.querySelectorAll("[data-reveal]");

    if (reducedMotion) {
        revealElements.forEach((element) => {
            element.classList.add("is-revealed");
        });
    } else {
        revealElements.forEach((element, index) => {
            setTimeout(() => {
                element.classList.add("is-revealed");
            }, 80 + index * 45);
        });
    }


    /*
     * Prevent accidental double submission on the simulator.
     *
     * This protects the UI from duplicate clicks.
     * It does not replace API idempotency.
     */
    document
        .querySelectorAll("form[data-single-submit]")
        .forEach((form) => {
            form.addEventListener("submit", () => {
                const submitButton =
                    form.querySelector(
                        "button[type='submit'], input[type='submit']"
                    );

                if (!submitButton) {
                    return;
                }

                submitButton.disabled = true;
                submitButton.classList.add(
                    "is-submitting"
                );

                const label =
                    submitButton.querySelector(
                        "[data-submit-label]"
                    );

                if (label) {
                    label.textContent = "Processing";
                }
            });
        });
});


document.addEventListener("DOMContentLoaded", () => {
    const currencyIcons = document.querySelectorAll(
        ".payment-currency-icon[data-currency]"
    );

    const currencySymbols = {
        USD: "$",
        EUR: "€",
        GBP: "£",
        INR: "₹",
        JPY: "¥",
        CNY: "¥",
        KRW: "₩",
        RUB: "₽",
        BRL: "R$",
        CAD: "$",
        AUD: "$",
        SGD: "$",
        HKD: "$",
        NZD: "$",
        CHF: "₣",
        SEK: "kr",
        NOK: "kr",
        DKK: "kr",
        PLN: "zł",
        TRY: "₺",
        ZAR: "R",
        AED: "د",
        SAR: "﷼",
        THB: "฿",
        IDR: "Rp",
        MYR: "RM",
        PHP: "₱",
        VND: "₫",
    };

    currencyIcons.forEach((icon) => {
        const currency = icon.dataset.currency
            ?.trim()
            .toUpperCase();

        if (!currency) {
            return;
        }

        const symbol = currencySymbols[currency] || currency;

        const target = icon.querySelector(
            ".payment-currency-symbol"
        );

        if (!target) {
            return;
        }

        target.textContent = symbol;

        /*
         * Three-letter fallback currencies need slightly
         * smaller typography to remain balanced inside
         * the circular mark.
         */
        if (!currencySymbols[currency]) {
            target.classList.add(
                "payment-currency-symbol-code"
            );
        }
    });
});