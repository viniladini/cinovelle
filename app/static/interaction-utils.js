/* Utilidades sem DOM para busca e mutações testáveis. */
(() => {
  function debounce(callback, delay = 300) {
    let timer;
    function delayed(...args) {
      clearTimeout(timer);
      timer = setTimeout(() => callback(...args), delay);
    }
    delayed.cancel = () => clearTimeout(timer);
    return delayed;
  }
  function mutationQueue() {
    let tail = Promise.resolve();
    return operation => {
      const next = tail.then(operation);
      tail = next.catch(() => {});
      return next;
    };
  }
  function latestSearch(fetcher) {
    let generation = 0;
    let controller;
    return {
      cancel() { generation += 1; controller?.abort(); },
      async run(url, receive, fail) {
        this.cancel();
        const current = generation;
        controller = new AbortController();
        try {
          const response = await fetcher(url, {signal: controller.signal, headers: {Accept: 'application/json'}});
          const data = await response.json();
          if (!response.ok) throw new Error(data.message);
          if (generation === current) receive(data);
        } catch (error) {
          if (generation === current && error.name !== 'AbortError') fail(error);
        }
      }
    };
  }
  globalThis.CinovelleUX = {debounce, mutationQueue, latestSearch};
})();
