use std::f64::consts::PI;

use pyo3::{exceptions::PyValueError, prelude::*};

#[pyclass]
struct ImageHash {
    bool_values: Vec<bool>,
    values: Vec<u8>,
    hash_size: usize,
}

#[pymethods]
impl ImageHash {
    #[getter]
    fn get_bool_values(&self) -> PyResult<Vec<bool>> {
        Ok(self.bool_values.clone())
    }

    #[getter]
    fn get_values(&self) -> PyResult<Vec<u8>> {
        Ok(self.values.clone())
    }

    #[getter]
    fn get_hash_size(&self) -> PyResult<usize> {
        Ok(self.hash_size)
    }

    pub fn distance(&self, other: &ImageHash) -> PyResult<u32> {
        if self.hash_size != other.hash_size {
            return Err(PyValueError::new_err("Unmatch size"));
        }

        let mut count = 0;
        let mut i: usize = 0;
        while i < self.hash_size.pow(2) {
            if self.bool_values.get(i).unwrap() != other.bool_values.get(i).unwrap() {
                count += 1
            };
            i += 1;
        }

        Ok(count)
    }
}

// Hashes an image using average hash
#[pyfunction]
fn ahash(fpath: String, hash_size: u32) -> PyResult<ImageHash> {
    let img = match image::open(fpath) {
        Ok(im) => im,
        Err(_e) => return Err(PyValueError::new_err("Cannot open image.")),
    };
    let resized = img
        .resize_exact(hash_size, hash_size, image::imageops::FilterType::Lanczos3)
        .to_luma8();

    let hashpow = hash_size.pow(2);
    let avg: f64 =
        resized.pixels().map(|px| px.0[0] as f64).sum::<f64>() / resized.pixels().len() as f64;

    let mut bool_result = vec![false; hashpow as usize];
    let mut result: Vec<u8> = vec![0; (hashpow / 8) as usize];

    for (c, px) in resized.pixels().enumerate() {
        let cmp = px.0[0] as f64 > avg;
        bool_result[c] = cmp;
        if cmp {
            result[c / 8] |= 1 << (c % 8);
        } else {
            result[c / 8] |= 0 << (c % 8);
        }
    }

    Ok(ImageHash {
        bool_values: bool_result,
        values: result,
        hash_size: hash_size as usize,
    })
}

// Hashes an image using perceptual hash
#[pyfunction]
fn phash(fpath: String, hash_size: u32, highfreq_factor: u32) -> PyResult<ImageHash> {
    let img = match image::open(fpath) {
        Ok(im) => im,
        Err(_e) => return Err(PyValueError::new_err("Cannot open image.")),
    };

    let img_size = hash_size * highfreq_factor;
    let resized = img
        .resize_exact(img_size, img_size, image::imageops::FilterType::Lanczos3)
        .to_luma8();

    let mut dct_arr =
        vec![vec![0.0f64; (hash_size + 1).try_into().unwrap()]; hash_size.try_into().unwrap()];

    for i in 0..hash_size {
        // Exclude first term of every y axis
        for j in 1..hash_size + 1 {
            #[allow(non_snake_case)]
            let N = img_size.pow(2) as f64;
            let k = (i * img_size + j) as f64;
            let mut sum = 0.0f64;

            for y in 0..img_size {
                for x in 0..img_size {
                    let value = resized.get_pixel(x, y).0[0] as f64;
                    let n = y * img_size + x;
                    sum += value * (PI / N * (n as f64 + 0.5) * k).cos();
                }
            }

            dct_arr[i as usize][(j - 1) as usize] = sum;
        }
    }

    let hashpow = hash_size.pow(2);
    let avg = dct_arr.iter().flat_map(|row| row.iter()).sum::<f64>() / hashpow as f64;

    let mut bool_result = vec![false; hashpow as usize];
    let mut result: Vec<u8> = vec![0; (hashpow / 8) as usize];

    for i in 0..hash_size {
        for j in 0..hash_size {
            let c = (i * hash_size + j) as usize;
            let cmp = dct_arr[i as usize][j as usize] > avg;
            bool_result[c] = cmp;
            if cmp {
                result[c / 8] |= 1 << (c % 8);
            } else {
                result[c / 8] |= 0 << (c % 8);
            }
        }
    }

    Ok(ImageHash {
        bool_values: bool_result,
        values: result,
        hash_size: hash_size as usize,
    })
}

// Hashes an image using difference hash
#[pyfunction]
fn dhash(fpath: String, hash_size: u32) -> PyResult<ImageHash> {
    let img = match image::open(fpath) {
        Ok(im) => im,
        Err(_e) => return Err(PyValueError::new_err("Cannot open image.")),
    };
    let resized = img
        .resize_exact(
            hash_size + 1,
            hash_size + 1,
            image::imageops::FilterType::Lanczos3,
        )
        .to_luma8();

    let hashpow = hash_size.pow(2);
    let mut bool_result = vec![false; hashpow as usize];
    let mut result: Vec<u8> = vec![0; (hashpow / 8) as usize];

    let mut y = 0;
    while y < hash_size {
        let mut x = 0;
        while x < hash_size {
            let c = (y * 8 + x) as usize;
            let left_pixel = resized.get_pixel(x, y).0[0];
            let right_pixel = resized.get_pixel(x + 1, y).0[0];

            let cmp = left_pixel > right_pixel;
            bool_result[c] = cmp;
            if cmp {
                result[c / 8] |= 1 << (c % 8);
            } else {
                result[c / 8] |= 0 << (c % 8);
            }

            x += 1;
        }
        y += 1;
    }

    Ok(ImageHash {
        bool_values: bool_result,
        values: result,
        hash_size: hash_size as usize,
    })
}

/// A Python module implemented in Rust.
#[pymodule]
fn dif(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<ImageHash>()?;
    m.add_function(wrap_pyfunction!(ahash, m)?)?;
    m.add_function(wrap_pyfunction!(dhash, m)?)?;
    m.add_function(wrap_pyfunction!(phash, m)?)?;
    Ok(())
}
