# aind-pophys-converter-capsule

Code Ocean capsule that runs the [`aind-pophys-converter`](https://github.com/AllenNeuralDynamics/aind-pophys-converter) library against AIND population physiology data assets. Converts raw ScanImage TIFFs to HDF5 and generates QC metrics for downstream aggregation.

All processing logic lives in [`aind-pophys-converter`](https://github.com/AllenNeuralDynamics/aind-pophys-converter).
See that repository's README for a full description of CLI parameters, the two processing paths
(Bergamo and mesoscope), module reference, and QC pipeline.
