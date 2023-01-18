use image::{GenericImageView, Pixel};
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
        return Ok(count);
    }
}

// Hashes an image
#[pyfunction]
fn hash_image(fpath: String, hash_size: u32) -> PyResult<ImageHash> {
    let img = match image::open(fpath) {
        Ok(im) => im,
        Err(_e) => return Err(PyValueError::new_err("Cannot open image.")),
    };
    let resized = img.resize_exact(hash_size, hash_size, image::imageops::FilterType::Nearest);

    let mut pixels = vec![vec![0; hash_size.try_into().unwrap()]; hash_size.try_into().unwrap()];

    let mut sum: u32 = 0;
    for pixel in resized.pixels() {
        let (x, y, rgb) = pixel;
        let px = rgb.to_luma();
        pixels[y as usize][x as usize] = px.0[0];
        sum += u32::from(px.0[0]);
    }

    let avg = sum / (u32::pow(hash_size, 2));
    let mut bool_result = vec![false; hash_size.pow(2).try_into().unwrap()];
    let mut result: Vec<u8> = vec![0; hash_size.try_into().unwrap()];
    let mut c = 0;
    for row_pxs in pixels {
        for px in row_pxs {
            let cmp = u32::from(px) > avg;
            bool_result[c] = cmp;
            if cmp {
                result[c / 8] |= 1 << (c % 8);
            } else {
                result[c / 8] |= 0 << (c % 8);
            }

            c += 1;
        }
    }

    return Ok(ImageHash {
        bool_values: bool_result,
        values: result,
        hash_size: hash_size as usize,
    });
}

/// A Python module implemented in Rust.
#[pymodule]
fn dif(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<ImageHash>()?;
    m.add_function(wrap_pyfunction!(hash_image, m)?)?;
    Ok(())
}
